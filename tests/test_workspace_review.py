"""Fictitious workspace results for the observed offline contract."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import unittest

from strategy_factory.workspace_review import review_definition, validate_workspace_result


FIXTURE = Path(__file__).parent / "fixtures" / "factory_workspace_tool.json"
MQL5 = "synthetic-installation/MQL5"
LOGIN = "synthetic-private-login"
PROJECTION = {"identity_confirmed": True, "mcp_calls_authorized": False}


def example_from_schema(schema):
    """Populate optional fields too, including array items."""
    kind = schema["type"]
    if kind == "object":
        return {
            key: example_from_schema(child)
            for key, child in schema["properties"].items()
        }
    if kind == "array":
        return [example_from_schema(schema["items"])]
    return {"string": "fictional", "boolean": True, "integer": 7}[kind]


class WorkspaceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def setUp(self):
        self.result = example_from_schema(self.tool["outputSchema"])
        self.result["workspace"]["mql5_folder"] = MQL5
        self.result["permissions"]["write_roots"] = [MQL5, f"{MQL5}/Experts"]
        self.result["community"]["community_login"] = LOGIN

    def validate(self):
        return validate_workspace_result(self.result, expected_mql5=MQL5)

    def test_definition_fingerprint_and_projection(self):
        canonical = json.dumps(
            self.tool, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        self.assertEqual(review_definition(dict(reversed(list(self.tool.items())))), {
            "status": "reviewed_offline_only",
            "mcp_calls_authorized": False,
            "definition_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        })

    def test_changed_description_is_rejected_without_echo(self):
        tool = dict(self.tool, description=LOGIN)
        with self.assertRaises(ValueError) as error:
            review_definition(tool)
        self.assertNotIn(LOGIN, str(error.exception))

    def test_changed_input_schema_is_rejected(self):
        tool = deepcopy(self.tool)
        tool["inputSchema"]["additionalProperties"] = True
        with self.assertRaises(ValueError):
            review_definition(tool)

    def test_changed_nested_annotation_is_rejected(self):
        tool = deepcopy(self.tool)
        tool["outputSchema"]["properties"]["community"]["description"] = LOGIN
        with self.assertRaises(ValueError):
            review_definition(tool)

    def test_changed_output_schema_version_contract_is_rejected(self):
        tool = deepcopy(self.tool)
        tool["outputSchema"]["properties"]["schema_version"]["type"] = "integer"
        with self.assertRaises(ValueError):
            review_definition(tool)

    def test_added_protocol_version_is_rejected(self):
        with self.assertRaises(ValueError):
            review_definition(dict(self.tool, protocolVersion="2025-03-26"))

    def test_nonserializable_definition_is_rejected(self):
        with self.assertRaises(ValueError):
            review_definition(dict(self.tool, description=object()))

    def test_complete_result_is_projected_without_account_or_permissions(self):
        original = deepcopy(self.result)
        self.assertEqual(self.validate(), PROJECTION)
        self.assertEqual(self.result, original)

    def test_required_top_level_properties(self):
        for key in list(self.result):
            with self.subTest(key=key):
                original = self.result.pop(key)
                with self.assertRaises(ValueError):
                    self.validate()
                self.result[key] = original

    def test_optional_nested_fields_can_be_absent(self):
        self.result = dict.fromkeys(self.result)
        for key in self.result:
            self.result[key] = {}
        self.result["schema_version"] = "fictitious-version"
        self.result["workspace"]["mql5_folder"] = MQL5
        self.assertEqual(self.validate(), PROJECTION)

    def test_missing_nested_identity_is_rejected(self):
        del self.result["workspace"]["mql5_folder"]
        with self.assertRaises(ValueError):
            self.validate()

    def test_structured_content_must_be_an_object(self):
        with self.assertRaises(ValueError):
            validate_workspace_result([self.result], expected_mql5=MQL5)

    def test_extra_keys_are_rejected_at_every_object_level(self):
        for obj in [self.result, *[v for v in self.result.values() if isinstance(v, dict)]]:
            with self.subTest(obj_size=len(obj)):
                obj["unrecognized"] = LOGIN
                with self.assertRaises(ValueError) as error:
                    self.validate()
                self.assertNotIn(LOGIN, str(error.exception))
                del obj["unrecognized"]

    def test_bool_is_not_integer(self):
        self.result["compiler"]["compiler_mql5_build"] = True
        with self.assertRaises(ValueError):
            self.validate()

    def test_integer_is_not_bool(self):
        self.result["permissions"]["can_delete_files"] = 1
        with self.assertRaises(ValueError):
            self.validate()

    def test_community_fields_must_have_the_observed_types(self):
        self.result["community"]["community_login"] = {"secret": LOGIN}
        with self.assertRaises(ValueError) as error:
            self.validate()
        self.assertNotIn(LOGIN, str(error.exception))

    def test_permission_roots_require_arrays_of_paths(self):
        for field in ("read_roots", "write_roots", "execute_roots"):
            original = self.result["permissions"][field]
            for invalid in (MQL5, (MQL5,), [True], [""]):
                with self.subTest(field=field, invalid=invalid):
                    self.result["permissions"][field] = invalid
                    with self.assertRaises(ValueError):
                        self.validate()
            self.result["permissions"][field] = original

    def test_unrelated_installation_with_same_folder_name_is_rejected(self):
        self.result["workspace"]["mql5_folder"] = "other-installation/MQL5"
        with self.assertRaises(ValueError):
            self.validate()

    def test_write_roots_must_stay_within_expected_folder(self):
        for root in ("synthetic-installation", f"{MQL5}-other", f"{MQL5}/../elsewhere"):
            with self.subTest(root=root):
                self.result["permissions"]["write_roots"] = [root]
                with self.assertRaises(ValueError):
                    self.validate()

    def test_windows_paths_are_compared_independently_of_host(self):
        expected = PureWindowsPath(r"C:/Synthetic/MQL5")
        self.result["workspace"]["mql5_folder"] = "c:/synthetic/mql5/"
        self.result["permissions"]["write_roots"] = [r"C:\Synthetic\MQL5\Experts"]
        self.assertEqual(
            validate_workspace_result(self.result, expected_mql5=expected), PROJECTION
        )


if __name__ == "__main__":
    unittest.main()
