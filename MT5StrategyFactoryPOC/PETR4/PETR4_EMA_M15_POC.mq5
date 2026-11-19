#property strict
#property version "1.00"
#include <Trade/Trade.mqh>
input int FastPeriod=9;
input int SlowPeriod=21;
input double Volume=100.0;
input ulong Magic=9021004;
CTrade trade;
int fast=INVALID_HANDLE,slow=INVALID_HANDLE;
datetime lastBar=0;
int OnInit()
{
   if(!MQLInfoInteger(MQL_TESTER)) { Print("Tester only: execution refused"); return INIT_FAILED; }
   if(FastPeriod<1 || SlowPeriod<=FastPeriod || Volume<=0) return INIT_PARAMETERS_INCORRECT;
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(step<=0 || Volume<SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN) || Volume>SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX) || MathAbs(Volume/step-MathRound(Volume/step))>1e-7) return INIT_PARAMETERS_INCORRECT;
   fast=iMA(_Symbol,_Period,FastPeriod,0,MODE_EMA,PRICE_CLOSE);
   slow=iMA(_Symbol,_Period,SlowPeriod,0,MODE_EMA,PRICE_CLOSE);
   if(fast==INVALID_HANDLE || slow==INVALID_HANDLE) return INIT_FAILED;
   trade.SetExpertMagicNumber(Magic);
   trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason)
{
   if(fast!=INVALID_HANDLE) IndicatorRelease(fast);
   if(slow!=INVALID_HANDLE) IndicatorRelease(slow);
}
bool Done() { return trade.ResultRetcode()==TRADE_RETCODE_DONE; }
void OnTick()
{
   datetime bar=iTime(_Symbol,_Period,0);
   if(bar==0 || bar==lastBar || BarsCalculated(fast)<SlowPeriod+2 || BarsCalculated(slow)<SlowPeriod+2) return;
   double f[2],s[2];
   // CopyBuffer stores the older closed bar (shift 2) first.
   if(CopyBuffer(fast,0,1,2,f)!=2 || CopyBuffer(slow,0,1,2,s)!=2) return;
   lastBar=bar;
   int signal=0;
   if(f[0]<=s[0] && f[1]>s[1]) signal=1;
   if(f[0]>=s[0] && f[1]<s[1]) signal=-1;
   if(signal==0) return;
   // Refuse to interfere with another EA/manual position on this symbol.
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=Magic) return;
   }
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=Magic) continue;
      long type=PositionGetInteger(POSITION_TYPE);
      if((signal==1 && type==POSITION_TYPE_BUY) || (signal==-1 && type==POSITION_TYPE_SELL)) return;
      if(!trade.PositionClose(ticket) || !Done()) { Print("Close failed: ",trade.ResultRetcode()," ",trade.ResultRetcodeDescription()); return; }
   }
   // Confirm all previous positions have closed before opening the reversal.
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetTicket(i)>0 && PositionGetString(POSITION_SYMBOL)==_Symbol) return;
   bool ok= signal==1 ? trade.Buy(Volume,_Symbol) : trade.Sell(Volume,_Symbol);
   if(!ok || !Done()) Print("Entry result: ",trade.ResultRetcode()," ",trade.ResultRetcodeDescription());
}

