#property strict
#property version "1.00"
#property description "Factory generated candidate: tester only, no optimization"
#include <Trade/Trade.mqh>
// Candidate: g1_fcb7f99b53c86641
// Specification SHA256: fcb7f99b53c86641f54781dc7f1741465afe9f898179d370021fcaf6091335c4
// Generator version: 1.0.0
// Indicators/signals use closed bars only: [0] is shift 2, [1] is shift 1.
const string CANDIDATE_ID="g1_fcb7f99b53c86641";
const string SPEC_SYMBOL="PETR4";
const ENUM_TIMEFRAMES SPEC_PERIOD=PERIOD_M5;
const ulong MAGIC=277867096921032;
const double SL_PERCENT=1.0;
const double TP_PERCENT=1.5;
const double MAX_SPREAD_POINTS=10.0;
const int MAX_ENTRIES=30;
const int MAX_HOLDING_BARS=24;
const int WARMUP=28;
const ulong DEVIATION=5;
CTrade g_trade;
datetime g_last_bar=0;
bool g_halted=false;
int g_entries=0,g_holding=0;
int h0=INVALID_HANDLE;
int h1=INVALID_HANDLE;

bool TesterOnly()
{
   return (bool)MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION);
}

void Halt(const string reason)
{
   g_halted=true;
   Print("FACTORY HALT candidate=",CANDIDATE_ID," reason=",reason);
}

int OnInit()
{
   // Guard before indicators or trading setup; failed initialization never trades.
   if(!TesterOnly()) return INIT_FAILED;
   if(_Symbol!=SPEC_SYMBOL || _Period!=SPEC_PERIOD) return INIT_PARAMETERS_INCORRECT;
   if(PositionsTotal()!=0 || OrdersTotal()!=0) return INIT_FAILED;
   long mode=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   if((true && mode!=SYMBOL_TRADE_MODE_FULL && mode!=SYMBOL_TRADE_MODE_LONGONLY) ||
      (true && mode!=SYMBOL_TRADE_MODE_FULL && mode!=SYMBOL_TRADE_MODE_SHORTONLY)) return INIT_FAILED;
   g_trade.SetExpertMagicNumber(MAGIC);
   g_trade.SetDeviationInPoints(DEVIATION);
   g_trade.SetAsyncMode(false);
   if(!g_trade.SetTypeFillingBySymbol(_Symbol)) return INIT_FAILED;
   h0=iADX(_Symbol,_Period,14);
   if(h0==INVALID_HANDLE) return INIT_FAILED;
   h1=iRSI(_Symbol,_Period,14,PRICE_CLOSE);
   if(h1==INVALID_HANDLE) return INIT_FAILED;
   Print("FACTORY INIT candidate=",CANDIDATE_ID," spec_sha256=fcb7f99b53c86641f54781dc7f1741465afe9f898179d370021fcaf6091335c4");
   return INIT_SUCCEEDED;
}

bool ClosedBuffer(const int handle,const int buffer,double &values[])
{
   if(BarsCalculated(handle)<WARMUP+3) return false;
   if(CopyBuffer(handle,buffer,1,2,values)!=2) return false;
   return MathIsValidNumber(values[0]) && MathIsValidNumber(values[1]) &&
          MathAbs(values[0])<1e100 && MathAbs(values[1])<1e100;
}

bool CloseOwned(const ulong ticket)
{
   if(!TesterOnly() || !PositionSelectByTicket(ticket)) return false;
   if(PositionGetString(POSITION_SYMBOL)!=_Symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=MAGIC) return false;
   bool sent=g_trade.PositionClose(ticket,DEVIATION);
   PrintFormat("FACTORY CLOSE candidate=%s ticket=%I64u retcode=%u",CANDIDATE_ID,ticket,g_trade.ResultRetcode());
   return sent && g_trade.ResultRetcode()==TRADE_RETCODE_DONE && PositionsTotal()==0 && OrdersTotal()==0;
}

void Enter(const bool buy)
{
   // Every function that can send a trade request has its own tester guard.
   if(!TesterOnly() || g_halted || g_entries>=MAX_ENTRIES || PositionsTotal()!=0 || OrdersTotal()!=0) return;
   double volume=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double maximum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   MqlTick tick;
   if(volume<=0 || step<=0 || maximum<volume || size<=0 || _Point<=0 ||
      MathAbs(volume/step-MathRound(volume/step))>0.000001 || !SymbolInfoTick(_Symbol,tick) ||
      tick.bid<=0 || tick.ask<tick.bid)
   { Halt("invalid symbol volume or quote"); return; }
   if(MAX_SPREAD_POINTS>=0 && (tick.ask-tick.bid)/_Point>MAX_SPREAD_POINTS) return;
   double price=buy ? tick.ask : tick.bid;
   double sl=buy ? MathFloor(price*(1-SL_PERCENT/100)/size)*size : MathCeil(price*(1+SL_PERCENT/100)/size)*size;
   double tp=buy ? MathCeil(price*(1+TP_PERCENT/100)/size)*size : MathFloor(price*(1-TP_PERCENT/100)/size)*size;
   sl=NormalizeDouble(sl,_Digits);
   tp=NormalizeDouble(tp,_Digits);
   double minimum=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   if(sl<=0 || tp<=0 || (buy && (sl>=tick.bid || tp<=tick.ask || tick.bid-sl<minimum || tp-tick.bid<minimum)) ||
      (!buy && (sl<=tick.ask || tp>=tick.bid || sl-tick.ask<minimum || tick.ask-tp<minimum)))
   { Halt("SL/TP constraints incompatible"); return; }
   double margin=0;
   if(!OrderCalcMargin(buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,_Symbol,volume,price,margin) ||
      !MathIsValidNumber(margin) || margin<0 || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE))
   { Halt("margin unavailable or insufficient"); return; }
   if(!TesterOnly() || PositionsTotal()!=0 || OrdersTotal()!=0) return;
   bool sent=buy ? g_trade.Buy(volume,_Symbol,0,sl,tp,CANDIDATE_ID) : g_trade.Sell(volume,_Symbol,0,sl,tp,CANDIDATE_ID);
   PrintFormat("FACTORY ENTRY candidate=%s buy=%s volume=%.8f retcode=%u",CANDIDATE_ID,buy ? "true" : "false",volume,g_trade.ResultRetcode());
   if(!sent || g_trade.ResultRetcode()!=TRADE_RETCODE_DONE || PositionsTotal()!=1 || OrdersTotal()!=0)
   { Halt("entry not fully confirmed; no retries"); return; }
   g_entries++;
   g_holding=0;
}

void OnTick()
{
   if(!TesterOnly() || g_halted) return;
   datetime bar=iTime(_Symbol,_Period,0); // Only new-bar scheduling, never a signal.
   if(bar==0 || bar==g_last_bar) return;
   double close[2];
   if(CopyClose(_Symbol,_Period,1,2,close)!=2) return;
   if(!MathIsValidNumber(close[0]) || !MathIsValidNumber(close[1]) || close[0]<=0 || close[1]<=0) return;
   double h0b0[2];
   if(!ClosedBuffer(h0,0,h0b0)) return;
   double h0b1[2];
   if(!ClosedBuffer(h0,1,h0b1)) return;
   double h0b2[2];
   if(!ClosedBuffer(h0,2,h0b2)) return;
   double h1b0[2];
   if(!ClosedBuffer(h1,0,h1b0)) return;
   g_last_bar=bar;
   if(OrdersTotal()!=0) { Halt("outstanding order"); return; }
   bool enter_long=(h0b0[1]>=0.0 && h0b0[1]<=25.0) && (h1b0[0]<=30.0 && h1b0[1]>30.0);
   bool enter_short=(h0b0[1]>=0.0 && h0b0[1]<=25.0) && (h1b0[0]>=70.0 && h1b0[1]<70.0);
   bool exit_long=(h1b0[1]>60.0);
   bool exit_short=(h1b0[1]<40.0);
   if(PositionsTotal()>0)
   {
      if(PositionsTotal()!=1) { Halt("multiple positions"); return; }
      ulong ticket=PositionGetTicket(0);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol ||
         (ulong)PositionGetInteger(POSITION_MAGIC)!=MAGIC)
      { Halt("position ownership mismatch"); return; }
      long side=PositionGetInteger(POSITION_TYPE);
      g_holding++;
      if(g_holding>=MAX_HOLDING_BARS || (side==POSITION_TYPE_BUY && exit_long) || (side==POSITION_TYPE_SELL && exit_short))
         if(!CloseOwned(ticket)) Halt("close not fully confirmed; no retries");
      return; // No same-bar flip, averaging or pyramiding.
   }
   if(enter_long==enter_short) return; // Conflicting entries are skipped.
   Enter(enter_long);
}

void OnDeinit(const int reason)
{
   if(h0!=INVALID_HANDLE) IndicatorRelease(h0);
   if(h1!=INVALID_HANDLE) IndicatorRelease(h1);
   // No trading in cleanup. A final close, if any, belongs to the Tester.
}

double OnTester()
{
   if(!TesterOnly()) return 0;
   ResetLastError();
   double result=TesterStatistics(STAT_PROFIT);
   if(GetLastError()!=0 || !MathIsValidNumber(result) || MathAbs(result)>=1e100)
   { Print("FACTORY RESULT candidate=",CANDIDATE_ID," profit=UNAVAILABLE"); return 0; }
   PrintFormat("FACTORY RESULT candidate=%s profit=%.10f",CANDIDATE_ID,result);
   return result;
}
