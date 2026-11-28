"""Closed execution profiles. Selecting a profile never authorizes a native run."""
from dataclasses import dataclass, asdict
from pathlib import PureWindowsPath


@dataclass(frozen=True)
class ExecutionProfile:
    name: str
    expert: PureWindowsPath
    source_sha256: str
    compiled_sha256: str
    positive_operations: bool = False


_ROOT = PureWindowsPath('C:/Users/User/AppData/Roaming/MetaQuotes/Terminal/AEF1E6F57078EAB3775179FCBD94D671/MQL5/Experts/MT5StrategyFactory')
HOMOLOGATION_001 = ExecutionProfile(
    'sf_o07_zero_operations', _ROOT / 'Homologacao_001/MT5SF_Homologacao_001.ex5',
    '78bd1d4b04ebe2805738081a193148df2a8bc2777820f27fc27b7a2eb3f6d22c',
    '9ed2ebeb5b6803eb4698bbf49cec643f876623bed9005b4d5278d2655b142854')
SF_O08 = ExecutionProfile(
    'sf_o08_ema5_20', _ROOT / 'SFO08/Homologacao_002/MT5SF_Homologacao_002.ex5',
    '228f06328b9aa1bcf86fb86004e9907caf11f24ced46aeb2257e1f549e335787',
    'b97c50a3a04f679dbadabd32ceaee19cb232f8ffd342761300094a32b7ce5b6d', True)


def checked_profile(profile):
    if profile is not HOMOLOGATION_001 and profile is not SF_O08:
        raise ValueError('unreviewed_execution_profile')
    return profile


def profile_record(profile):
    record = asdict(checked_profile(profile))
    record['expert'] = str(profile.expert)
    return record


def validate_scenario(config, profile):
    checked_profile(profile)
    if profile is SF_O08 and (
        config.symbol != 'EURUSD' or config.timeframe != 'M5' or
        config.from_date != '2023-11-01' or config.to_date != '2023-11-02' or
        config.model != 'm1 ohlc' or config.currency != 'USD' or
        config.deposit != 10000 or config.leverage != 1 or config.execution_delay != 0
    ):
        raise ValueError('sf_o08_scenario_not_reviewed')
