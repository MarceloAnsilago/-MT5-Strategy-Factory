// Isolated script: synthetic records only, no EA, market/history or trading calls.
// Compile/run separately only after authorization. Does not start Strategy Tester.
#property strict
#property script_show_inputs
#include "../FinalReportTotals.mqh"

int failures=0;
void Expect(const bool condition,const string label)
{
   if(!condition) { failures++; Print("FAIL: ",label); }
}

void OnStart()
{
   FinalReportTotals confirmed,inconclusive;
   FinalReportReset(confirmed);
   FinalReportReset(inconclusive);
   // Historical fixture: two entries, one TP, one unobserved end-of-test exit.
   // The caller supplies the buckets; the reducer NEVER infers ownership.
   FinalReportAdd(confirmed,true,true,true,0,0,0,0);
   FinalReportAdd(confirmed,true,true,true,89,0,0,0);
   FinalReportAdd(confirmed,true,true,true,0,0,0,0);
   FinalReportAdd(inconclusive,false,false,true,-4,0,0,0);
   Expect(confirmed.net==89 && inconclusive.net==-4,"separate +89 and -4");
   Expect(confirmed.net+inconclusive.net==85,"global reconciliation +85");
   Expect(confirmed.records==3 && inconclusive.records==1,"deal counts, not round trips");
   Expect(confirmed.callback_seen==3 && confirmed.history_only==0,"confirmed callbacks");
   Expect(inconclusive.callback_seen==0 && inconclusive.history_only==1,"history-only inconclusive");
   Expect(FinalReportMoney(false,0)=="UNAVAILABLE","unknown is never zero");
   Expect(FinalReportMoney(true,0)=="0.00","known zero remains available");
   Expect(FinalReportMoney(true,inconclusive.net)=="-4.00","inconclusive has known money, not ownership");
   Expect(FinalReportAvailable(confirmed,true),"complete group available");
   Expect(!FinalReportAvailable(confirmed,false),"incomplete snapshot hides even confirmed total");
   Expect(!FinalReportAvailable(inconclusive,false),"incomplete snapshot hides inconclusive total");

   FinalReportReset(inconclusive);
   FinalReportAdd(inconclusive,false,false,false,0,0,0,0);
   Expect(!inconclusive.money_available,"failed field read");
   FinalReportAdd(inconclusive,true,false,true,10,0,0,0);
   Expect(!inconclusive.money_available,"unavailability stays sticky");
   Expect(FinalReportMoney(inconclusive.money_available,inconclusive.net)=="UNAVAILABLE","partial sum hidden");
   Expect(inconclusive.records==2 && inconclusive.callback_processed==0,"observed versus processed");

   FinalReportReset(inconclusive);
   FinalReportAdd(inconclusive,true,true,true,10,-2,-1,-0.5);
   Expect(inconclusive.gross==10 && inconclusive.costs==-3.5 && inconclusive.net==6.5,"all cost fields");
   double invalid=MathSqrt(-1.0);
   FinalReportAdd(inconclusive,false,false,true,invalid,0,0,0);
   Expect(!inconclusive.money_available,"non-finite money");
   Expect(FinalReportMoney(true,invalid)=="UNAVAILABLE","non-finite formatting");
   FinalReportReset(inconclusive);
   Expect(inconclusive.money_available && inconclusive.net==0 && inconclusive.records==0,"fresh final pass, no double count");
   FinalReportAdd(inconclusive,false,false,true,1e308,0,0,0);
   FinalReportAdd(inconclusive,false,false,true,1e308,0,0,0);
   Expect(!inconclusive.money_available,"overflow unavailable");

   string long_text="";
   for(int i=0;i<2000;++i) long_text+="x";
   string rebuilt="";
   int parts=(StringLen(long_text)+179)/180;
   for(int i=0;i<parts;++i)
   {
      string chunk=FinalReportChunk(long_text,i);
      Expect(StringLen(chunk)<=180,"chunk limit");
      rebuilt+=chunk;
   }
   Expect(rebuilt==long_text,"all evidence retained across chunks");
   Expect(FinalReportChunk("a\r\nb",0)=="a  b","newlines sanitized");
   Expect(FinalReportChunk("",0)=="" && FinalReportChunk("a",-1)=="","empty/negative chunk");
   PrintFormat("REPORT_TEST_RESULT failures=%d",failures);
}
