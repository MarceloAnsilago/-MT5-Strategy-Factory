// v1.23 reporting only. No trading, history selection or ownership decisions.
#ifndef MT5SF_FINAL_REPORT_TOTALS_MQH
#define MT5SF_FINAL_REPORT_TOTALS_MQH

struct FinalReportTotals
{
   int records;
   int callback_seen;
   int history_only;
   int callback_processed;
   double gross;
   double costs;
   double net;
   bool money_available;
};

void FinalReportReset(FinalReportTotals &total)
{
   total.records=0;
   total.callback_seen=0;
   total.history_only=0;
   total.callback_processed=0;
   total.gross=0;
   total.costs=0;
   total.net=0;
   total.money_available=true;
}

// A false availability flag is sticky; default/failed reads never become zero PnL.
void FinalReportAdd(FinalReportTotals &total,const bool seen,const bool processed,
                    const bool readable,const double profit,const double commission,
                    const double swap,const double fee)
{
   total.records++;
   if(seen) total.callback_seen++;
   else total.history_only++;
   if(processed) total.callback_processed++;
   if(!readable || !MathIsValidNumber(profit) || !MathIsValidNumber(commission) ||
      !MathIsValidNumber(swap) || !MathIsValidNumber(fee))
   { total.money_available=false; return; }
   double next_gross=total.gross+profit;
   double next_costs=total.costs+commission+swap+fee;
   double next_net=next_gross+next_costs;
   if(!MathIsValidNumber(next_gross) || !MathIsValidNumber(next_costs) ||
      !MathIsValidNumber(next_net))
   { total.money_available=false; return; }
   total.gross=next_gross;
   total.costs=next_costs;
   total.net=next_net;
}

bool FinalReportAvailable(const FinalReportTotals &total,const bool complete)
{
   return complete && total.money_available;
}

string FinalReportMoney(const bool available,const double value)
{
   if(!available || !MathIsValidNumber(value)) return "UNAVAILABLE";
   return DoubleToString(value,2);
}

// UTF-16 payload chunks of at most 180 characters; newline-safe for journals.
// Prefix + payload stays well below the observed ~512-character truncation.
string FinalReportChunk(const string text,const int index)
{
   string safe=text;
   StringReplace(safe,"\r"," ");
   StringReplace(safe,"\n"," ");
   if(index<0 || index*180>=StringLen(safe)) return "";
   return StringSubstr(safe,index*180,180);
}

void FinalReportLine(const string phase,const string key,const string text)
{
   int parts=(StringLen(text)+179)/180;
   if(parts<1) parts=1;
   for(int i=0;i<parts;++i)
      PrintFormat("MT5SF001 FINAL phase=%s section=%s part=%d/%d %s",
                  phase,key,i+1,parts,FinalReportChunk(text,i));
}
#endif
