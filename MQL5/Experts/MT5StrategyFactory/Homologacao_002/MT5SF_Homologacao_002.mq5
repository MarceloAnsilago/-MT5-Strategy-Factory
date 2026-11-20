#property strict
#property version "1.00"
#property description "Factory homologation only: closed-bar EMA crossover, long only"
#include <Trade/Trade.mqh>

input int InpFastPeriod=9;
input int InpSlowPeriod=21;
input double InpStopLossPercent=1.0;
input double InpTakeProfitPercent=2.0;
input ulong InpMagic=20261123002;
input ulong InpDeviationPoints=5;

CTrade g_trade;
int g_fast=INVALID_HANDLE, g_slow=INVALID_HANDLE;
datetime g_last_bar=0;
bool g_halted=false;

bool TesterOnly()
{
   return (bool)MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION);
}

int OnInit()
{
   // No indicator creation or trading initialization before this guard.
   if(!TesterOnly())
   {
      Print("MT5SF002 REFUSED: standalone tester only, optimization forbidden");
      return INIT_FAILED;
   }
   if(InpFastPeriod<2 || InpSlowPeriod<=InpFastPeriod ||
      !MathIsValidNumber(InpStopLossPercent) || InpStopLossPercent<=0 || InpStopLossPercent>=100 ||
      !MathIsValidNumber(InpTakeProfitPercent) || InpTakeProfitPercent<=0 ||
      InpMagic==0 || PositionsTotal()!=0 || OrdersTotal()!=0)
      return INIT_PARAMETERS_INCORRECT;
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   g_trade.SetAsyncMode(false);
   if(!g_trade.SetTypeFillingBySymbol(_Symbol)) return INIT_FAILED;
   g_fast=iMA(_Symbol,_Period,InpFastPeriod,0,MODE_EMA,PRICE_CLOSE);
   g_slow=iMA(_Symbol,_Period,InpSlowPeriod,0,MODE_EMA,PRICE_CLOSE);
   if(g_fast==INVALID_HANDLE || g_slow==INVALID_HANDLE) return INIT_FAILED;
   PrintFormat("MT5SF002 INIT symbol=%s period=%s min_volume=%.8f SL=%.4f TP=%.4f",
               _Symbol,EnumToString(_Period),SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),
               InpStopLossPercent,InpTakeProfitPercent);
   return INIT_SUCCEEDED;
}

void Halt(const string reason)
{
   g_halted=true;
   Print("MT5SF002 HALT ",reason);
}

void OnTick()
{
   if(!TesterOnly() || g_halted) return;
   datetime bar=iTime(_Symbol,_Period,0);
   if(bar==0 || bar==g_last_bar) return;
   if(BarsCalculated(g_fast)<InpSlowPeriod+3 || BarsCalculated(g_slow)<InpSlowPeriod+3) return;
   double fast[2],slow[2];
   // CopyBuffer writes the older closed bar to [0], newer closed bar to [1].
   if(CopyBuffer(g_fast,0,1,2,fast)!=2 || CopyBuffer(g_slow,0,1,2,slow)!=2) return;
   g_last_bar=bar;
   if(OrdersTotal()!=0) { Halt("outstanding order, no further requests"); return; }
   bool up=(fast[0]<=slow[0] && fast[1]>slow[1]);
   bool down=(fast[0]>=slow[0] && fast[1]<slow[1]);
   if(PositionsTotal()>0)
   {
      if(PositionsTotal()!=1) { Halt("unexpected number of positions"); return; }
      ulong ticket=PositionGetTicket(0);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol ||
         (ulong)PositionGetInteger(POSITION_MAGIC)!=InpMagic ||
         PositionGetInteger(POSITION_TYPE)!=POSITION_TYPE_BUY)
      { Halt("position ownership or direction mismatch"); return; }
      if(down)
      {
         if(!TesterOnly()) return;
         bool sent=g_trade.PositionClose(ticket,InpDeviationPoints);
         PrintFormat("MT5SF002 CLOSE ticket=%I64u retcode=%u",ticket,g_trade.ResultRetcode());
         if(!sent || g_trade.ResultRetcode()!=TRADE_RETCODE_DONE || PositionsTotal()!=0 || OrdersTotal()!=0)
            Halt("close not fully confirmed; no retries");
      }
      return; // Never close and reopen on the same bar.
   }
   if(!up) return;
   double volume=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double maximum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   MqlTick tick;
   if(volume<=0 || step<=0 || maximum<volume || tick_size<=0 ||
      MathAbs(volume/step-MathRound(volume/step))>0.000001 ||
      !SymbolInfoTick(_Symbol,tick) || tick.ask<=0 || tick.bid<=0)
   { Halt("invalid symbol volume or prices"); return; }
   int digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double sl=NormalizeDouble(MathFloor(tick.ask*(1-InpStopLossPercent/100)/tick_size)*tick_size,digits);
   double tp=NormalizeDouble(MathCeil(tick.ask*(1+InpTakeProfitPercent/100)/tick_size)*tick_size,digits);
   double minimum=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   if(sl<=0 || sl>=tick.bid || tp<=tick.ask || tick.bid-sl<minimum || tp-tick.bid<minimum)
   { Halt("SL/TP incompatible with current symbol constraints"); return; }
   // Recheck immediately before the sole entry request. No pending-order strategy.
   if(!TesterOnly() || PositionsTotal()!=0 || OrdersTotal()!=0) return;
   bool sent=g_trade.Buy(volume,_Symbol,0,sl,tp,"MT5SF002 tester only");
   PrintFormat("MT5SF002 BUY volume=%.8f SL=%.8f TP=%.8f retcode=%u deal=%I64u order=%I64u",
               volume,sl,tp,g_trade.ResultRetcode(),g_trade.ResultDeal(),g_trade.ResultOrder());
   if(!sent || g_trade.ResultRetcode()!=TRADE_RETCODE_DONE || PositionsTotal()!=1 || OrdersTotal()!=0)
      Halt("entry not fully confirmed; no retries or volume increases");
}

void Emit(const string name,const double value)
{
   if(!MathIsValidNumber(value) || MathAbs(value)>=1e100)
      PrintFormat("MT5SF002 STAT name=%s value=UNAVAILABLE",name);
   else
      PrintFormat("MT5SF002 STAT name=%s value=%.10f",name,value);
}

double ReadStatistic(const ENUM_STATISTICS id)
{
   ResetLastError();
   double value=TesterStatistics(id);
   if(GetLastError()!=0 || !MathIsValidNumber(value)) return DBL_MAX;
   return value;
}

double OnTester()
{
   if(!TesterOnly()) return 0;
   double initial=ReadStatistic(STAT_INITIAL_DEPOSIT);
   double trades=ReadStatistic(STAT_TRADES);
   double wins=ReadStatistic(STAT_PROFIT_TRADES);
   double loss=ReadStatistic(STAT_GROSS_LOSS);
   Emit("initial_balance",initial);
   ResetLastError();
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   if(GetLastError()!=0) balance=DBL_MAX;
   Emit("final_balance",balance);
   Emit("net_profit",ReadStatistic(STAT_PROFIT));
   Emit("gross_profit",ReadStatistic(STAT_GROSS_PROFIT));
   Emit("gross_loss",loss);
   // DBL_MAX is MT5's no-loss sentinel, not a finite usable profit factor.
   if(loss==0) Print("MT5SF002 STAT name=profit_factor value=UNAVAILABLE");
   else Emit("profit_factor",ReadStatistic(STAT_PROFIT_FACTOR));
   double balance_min=ReadStatistic(STAT_BALANCEMIN);
   double equity_min=ReadStatistic(STAT_EQUITYMIN);
   Emit("balance_drawdown_absolute",initial<1e100 && MathAbs(balance_min)<1e100 ? MathMax(0,initial-balance_min) : DBL_MAX);
   Emit("balance_drawdown_relative",ReadStatistic(STAT_BALANCE_DDREL_PERCENT));
   Emit("equity_drawdown_absolute",initial<1e100 && MathAbs(equity_min)<1e100 ? MathMax(0,initial-equity_min) : DBL_MAX);
   Emit("equity_drawdown_relative",ReadStatistic(STAT_EQUITY_DDREL_PERCENT));
   Emit("trades",trades);
   Emit("deals",ReadStatistic(STAT_DEALS));
   Emit("winning_trades",wins);
   Emit("losing_trades",ReadStatistic(STAT_LOSS_TRADES));
   if(trades>0 && trades<1e100 && wins>=0 && wins<=trades)
   {
      Emit("win_rate",100*wins/trades);
      Emit("expected_payoff",ReadStatistic(STAT_EXPECTED_PAYOFF));
   }
   else
   {
      Print("MT5SF002 STAT name=win_rate value=UNAVAILABLE");
      Print("MT5SF002 STAT name=expected_payoff value=UNAVAILABLE");
   }
   double result=ReadStatistic(STAT_PROFIT);
   return MathAbs(result)<1e100 ? result : 0;
}

void OnDeinit(const int reason)
{
   // No trade request in cleanup. Tester handles any forced end-of-test close.
   if(g_fast!=INVALID_HANDLE) IndicatorRelease(g_fast);
   if(g_slow!=INVALID_HANDLE) IndicatorRelease(g_slow);
}
