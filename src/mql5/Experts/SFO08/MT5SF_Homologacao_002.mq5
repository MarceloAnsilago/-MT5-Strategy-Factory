#property strict
#property version "2.00"
#property description "SF-O08: EURUSD M5 EMA5/20, fixed 0.01, standalone demo Tester only"
#include <Trade/Trade.mqh>
// Separate from the historical long-only Homologacao_002 and Homologacao_001.
const string STRATEGY_ID="SF-O08-H002-EMA5-20-v1";
const string SPEC_SHA256="6a7be176395f20b0c22c15682f6f896ce04840dd917718502f306c27bee8da74";
const ulong MAGIC=117080296143199;
const double LOTS=0.01;
const ulong DEVIATION=5;
input string InpRunId="";
CTrade g_trade;
int g_fast=INVALID_HANDLE,g_slow=INVALID_HANDLE;
datetime g_last_bar=0;
bool g_halted=false;
int g_deferred=0;
uint g_requests=0,g_rejections=0,g_errors=0,g_buys=0,g_sells=0,g_closes=0;

bool TesterOnly()
{
   return (bool)MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION) &&
          !MQLInfoInteger(MQL_FORWARD) && AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO;
}

bool ValidRunId()
{
   if(StringLen(InpRunId)!=38 || StringSubstr(InpRunId,0,6)!="local_") return false;
   for(int i=6;i<38;i++)
   {
      ushort c=StringGetCharacter(InpRunId,i);
      if(!((c>=48 && c<=57) || (c>=97 && c<=102))) return false;
   }
   return true;
}

void Halt(const string reason)
{
   if(!g_halted) g_errors++;
   g_halted=true;
   PrintFormat("SFO08 HALT strategy=%s run=%s reason=%s",STRATEGY_ID,InpRunId,reason);
}

bool VolumeAllowed()
{
   double minimum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double maximum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   return MathIsValidNumber(minimum) && MathIsValidNumber(maximum) && MathIsValidNumber(step) &&
          minimum>0 && step>0 && minimum<=LOTS && LOTS<=maximum &&
          MathAbs(LOTS/step-MathRound(LOTS/step))<0.00000001;
}

bool OwnedPosition(const int side)
{
   if(PositionsTotal()!=1 || OrdersTotal()!=0) return false;
   ulong ticket=PositionGetTicket(0);
   return ticket!=0 && PositionSelectByTicket(ticket) &&
          PositionGetString(POSITION_SYMBOL)==_Symbol &&
          (ulong)PositionGetInteger(POSITION_MAGIC)==MAGIC &&
          PositionGetInteger(POSITION_TYPE)==side &&
          MathAbs(PositionGetDouble(POSITION_VOLUME)-LOTS)<0.00000001;
}

int OnInit()
{
   // No indicators or trade initialization before the standalone Tester guard.
   if(!TesterOnly()) return INIT_FAILED;
   if(_Symbol!="EURUSD" || _Period!=PERIOD_M5 || !ValidRunId()) return INIT_PARAMETERS_INCORRECT;
   if(PositionsTotal()!=0 || OrdersTotal()!=0 || !VolumeAllowed() ||
      SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE)!=SYMBOL_TRADE_MODE_FULL) return INIT_FAILED;
   g_trade.SetExpertMagicNumber(MAGIC);
   g_trade.SetDeviationInPoints(DEVIATION);
   g_trade.SetAsyncMode(false);
   if(!g_trade.SetTypeFillingBySymbol(_Symbol)) return INIT_FAILED;
   g_fast=iMA(_Symbol,PERIOD_M5,5,0,MODE_EMA,PRICE_CLOSE);
   g_slow=iMA(_Symbol,PERIOD_M5,20,0,MODE_EMA,PRICE_CLOSE);
   if(g_fast==INVALID_HANDLE || g_slow==INVALID_HANDLE) return INIT_FAILED;
   PrintFormat("SFO08 INIT strategy=%s run=%s spec=%s magic=%I64u symbol=EURUSD timeframe=M5",
               STRATEGY_ID,InpRunId,SPEC_SHA256,MAGIC);
   return INIT_SUCCEEDED;
}

bool ClosedBuffer(const int handle,double &values[])
{
   if(BarsCalculated(handle)<23 || CopyBuffer(handle,0,1,2,values)!=2) return false;
   // Physical index 0 is shift 2; index 1 is shift 1. Never signal on shift 0.
   return MathIsValidNumber(values[0]) && MathIsValidNumber(values[1]) &&
          values[0]>0 && values[1]>0 && values[0]!=EMPTY_VALUE && values[1]!=EMPTY_VALUE;
}

void CloseOwned(const ulong ticket)
{
   if(!TesterOnly() || !PositionSelectByTicket(ticket) ||
      PositionGetString(POSITION_SYMBOL)!=_Symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=MAGIC)
   { Halt("close_ownership_or_tester"); return; }
   g_requests++;
   bool sent=g_trade.PositionClose(ticket,DEVIATION);
   uint code=g_trade.ResultRetcode();
   PrintFormat("SFO08 ORDER strategy=%s run=%s action=close sent=%d retcode=%u deal=%I64u order=%I64u",
               STRATEGY_ID,InpRunId,(int)sent,code,g_trade.ResultDeal(),g_trade.ResultOrder());
   if(!sent || code!=TRADE_RETCODE_DONE)
   { g_rejections++; Halt("close_rejected_or_partial_no_retry"); return; }
   if(PositionsTotal()!=0 || OrdersTotal()!=0) { Halt("close_state_not_confirmed"); return; }
   g_closes++;
}

void OpenFixed(const int signal)
{
   if(!TesterOnly() || PositionsTotal()!=0 || OrdersTotal()!=0 || !VolumeAllowed())
   { Halt("entry_state_or_volume"); return; }
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick) || !MathIsValidNumber(tick.ask) || !MathIsValidNumber(tick.bid) ||
      tick.ask<=0 || tick.bid<=0 || tick.ask<tick.bid) { Halt("invalid_quote"); return; }
   double margin=0;
   if(!OrderCalcMargin(signal>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,_Symbol,LOTS,
                       signal>0 ? tick.ask : tick.bid,margin) || !MathIsValidNumber(margin) ||
      margin<0 || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)) { Halt("margin_unavailable"); return; }
   if(!TesterOnly() || PositionsTotal()!=0 || OrdersTotal()!=0) { Halt("pre_request_state_changed"); return; }
   g_requests++;
   bool sent=signal>0 ? g_trade.Buy(LOTS,_Symbol,0,0,0,STRATEGY_ID) :
                        g_trade.Sell(LOTS,_Symbol,0,0,0,STRATEGY_ID);
   uint code=g_trade.ResultRetcode();
   PrintFormat("SFO08 ORDER strategy=%s run=%s action=%s sent=%d retcode=%u deal=%I64u order=%I64u",
               STRATEGY_ID,InpRunId,signal>0 ? "buy" : "sell",(int)sent,code,g_trade.ResultDeal(),g_trade.ResultOrder());
   if(!sent || code!=TRADE_RETCODE_DONE)
   { g_rejections++; Halt("entry_rejected_or_partial_no_retry"); return; }
   if(!OwnedPosition(signal>0 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL) ||
      MathAbs(g_trade.ResultVolume()-LOTS)>0.00000001) { Halt("entry_state_not_confirmed"); return; }
   if(signal>0) g_buys++; else g_sells++;
}

void OnTick()
{
   if(!TesterOnly() || g_halted) return;
   datetime bar=iTime(_Symbol,PERIOD_M5,0); // Scheduling only, not signal data.
   if(bar<=0 || bar<=g_last_bar) return;
   double fast[2],slow[2];
   if(!ClosedBuffer(g_fast,fast) || !ClosedBuffer(g_slow,slow)) return;
   g_last_bar=bar; // Consume once before any request, including rejected requests.
   if(OrdersTotal()!=0 || PositionsTotal()>1) { Halt("unexpected_exposure"); return; }
   bool up=fast[0]<=slow[0] && fast[1]>slow[1];
   bool down=fast[0]>=slow[0] && fast[1]<slow[1];
   if(PositionsTotal()==1)
   {
      ulong ticket=PositionGetTicket(0);
      if(ticket==0) { Halt("position_unavailable"); return; }
      int side=(int)PositionGetInteger(POSITION_TYPE);
      if((side!=POSITION_TYPE_BUY && side!=POSITION_TYPE_SELL) || !OwnedPosition(side))
      { Halt("foreign_or_unexpected_position"); return; }
      if((side==POSITION_TYPE_BUY && down) || (side==POSITION_TYPE_SELL && up))
      {
         CloseOwned(ticket);
         if(!g_halted) g_deferred=up ? 1 : -1;
      }
      return; // A reversal can open only on the next bar after full close confirmation.
   }
   if(g_deferred!=0)
   {
      int direction=g_deferred;
      g_deferred=0; // Single use; cancel if the new closed candle invalidates the direction.
      if((direction>0 && fast[1]>slow[1]) || (direction<0 && fast[1]<slow[1]))
      { OpenFixed(direction); return; }
   }
   if(up) OpenFixed(1); else if(down) OpenFixed(-1);
}

double Statistic(const ENUM_STATISTICS key)
{
   ResetLastError();
   double value=TesterStatistics(key);
   return GetLastError()==0 && MathIsValidNumber(value) && MathAbs(value)<1e100 ? value : DBL_MAX;
}

void Emit(const string key,const double value)
{
   if(!MathIsValidNumber(value) || MathAbs(value)>=1e100)
      PrintFormat("SFO08 STAT strategy=%s run=%s name=%s value=UNAVAILABLE",STRATEGY_ID,InpRunId,key);
   else PrintFormat("SFO08 STAT strategy=%s run=%s name=%s value=%.10f",STRATEGY_ID,InpRunId,key,value);
}

double OnTester()
{
   if(!TesterOnly() || !ValidRunId()) return 0;
   Emit("trades",Statistic(STAT_TRADES)); Emit("deals",Statistic(STAT_DEALS));
   Emit("net_profit",Statistic(STAT_PROFIT));
   Emit("balance_drawdown_relative",Statistic(STAT_BALANCE_DDREL_PERCENT));
   Emit("equity_drawdown_relative",Statistic(STAT_EQUITY_DDREL_PERCENT));
   double initial=Statistic(STAT_INITIAL_DEPOSIT),balance_min=Statistic(STAT_BALANCEMIN),equity_min=Statistic(STAT_EQUITYMIN);
   Emit("balance_drawdown_absolute",initial<1e100 && balance_min<1e100 ? MathMax(0,initial-balance_min) : DBL_MAX);
   Emit("equity_drawdown_absolute",initial<1e100 && equity_min<1e100 ? MathMax(0,initial-equity_min) : DBL_MAX);
   double loss=Statistic(STAT_GROSS_LOSS);
   Emit("profit_factor",MathAbs(loss)<1e100 && loss<0 ? Statistic(STAT_PROFIT_FACTOR) : DBL_MAX);
   if(HistorySelect(0,TimeCurrent()))
   {
      int orders=0,deals=0;
      for(int i=0;i<HistoryOrdersTotal();i++)
      {
         ResetLastError();
         ulong ticket=HistoryOrderGetTicket(i);
         if(ticket==0) { orders=-1; break; }
         string symbol=HistoryOrderGetString(ticket,ORDER_SYMBOL);
         ulong magic=(ulong)HistoryOrderGetInteger(ticket,ORDER_MAGIC);
         if(GetLastError()!=0) { orders=-1; break; }
         if(symbol==_Symbol && magic==MAGIC) orders++;
      }
      for(int i=0;i<HistoryDealsTotal();i++)
      {
         ResetLastError();
         ulong ticket=HistoryDealGetTicket(i);
         if(ticket==0) { deals=-1; break; }
         long kind=HistoryDealGetInteger(ticket,DEAL_TYPE);
         string symbol=HistoryDealGetString(ticket,DEAL_SYMBOL);
         ulong magic=(ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC);
         if(GetLastError()!=0) { deals=-1; break; }
         if((kind==DEAL_TYPE_BUY || kind==DEAL_TYPE_SELL) && symbol==_Symbol && magic==MAGIC) deals++;
      }
      Emit("orders",orders>=0 ? (double)orders : DBL_MAX);
      Emit("owned_market_deals",deals>=0 ? (double)deals : DBL_MAX);
   }
   else { Emit("orders",DBL_MAX); Emit("owned_market_deals",DBL_MAX); }
   PrintFormat("SFO08 END strategy=%s run=%s requests=%u rejected=%u errors=%u buys=%u sells=%u closes=%u halted=%d",
               STRATEGY_ID,InpRunId,g_requests,g_rejections,g_errors,g_buys,g_sells,g_closes,(int)g_halted);
   double profit=Statistic(STAT_PROFIT);
   return profit<1e100 ? profit : 0;
}

void OnDeinit(const int reason)
{
   // No trade requests here; the Tester owns forced end-of-test liquidation.
   if(g_fast!=INVALID_HANDLE) IndicatorRelease(g_fast);
   if(g_slow!=INVALID_HANDLE) IndicatorRelease(g_slow);
}
