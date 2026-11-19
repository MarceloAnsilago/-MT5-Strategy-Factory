// MT5 Strategy Factory - Estrategia 001 v1.22. STRATEGY TESTER ONLY.
// Ownership has three outcomes. Failed reads are inconclusive, never assumed mixed.
// Read-only reconciliation has a finite input-controlled attempt budget.
// Diagnostic caps affect logging only, never safety decisions or recovery budgets.
// Closed-bar EMA crossover. No grid, martingale, pyramiding or reversal.
// All entry requests contain SL and TP. FOK only.
// Recovery: at most ONE repair and ONE close request per position identifier,
// and ONE removal request per active order ticket. Budgets are recorded in
// emulated Tester global variables BEFORE checking/sending, surviving EA reinit
// while that Tester environment retains them. No timer or retry loops.
// On reinitialization the actual exposure and complete position history are
// inspected again. Previous in-memory flags are NEVER treated as evidence.
// Percentages are nominal distances, NOT guaranteed realized loss/profit limits.
// Gaps/slippage can exceed 1%. Recovery can be rejected by market/server rules.
// Unknown/mixed ownership => ALERT + HALT, never change third-party exposure.
// Magic must be exclusive: another program using the same magic is indistinguishable.
#property strict
#property version "1.22"
#property description "EMA crossover with bounded protection recovery; Tester only"
#include <Trade/Trade.mqh>

input string             InpSymbol          = "PETR4";
input ENUM_TIMEFRAMES    InpTimeframe       = PERIOD_M5;
input int                InpFastPeriod      = 9;
input int                InpSlowPeriod      = 21;
input ENUM_APPLIED_PRICE InpAppliedPrice    = PRICE_CLOSE;
input double             InpShares          = 100.0;
input double             InpStopLossPercent = 1.0;
input double             InpTakeProfitPercent = 2.0;
input ulong              InpMagic           = 20261118001;
input ulong              InpDeviationPoints = 5;


input bool   InpDiagnosticEnabled       = true;
input int    InpDiagnosticMaxRecords    = 400;
input int    InpOwnershipMaxRecords     = 600;
input int    InpOwnershipFailureMaxRecords = 200;
input int    InpFinalMaxDetails         = 100;
input int    InpReconcileMaxAttempts    = 12;
input int    InpDiagnosticWindowTicks   = 8;
input double InpEquityExtremeStep       = 1.0;
// Diagnostic limits never disable ownership validation or recovery protections.
enum OwnershipState { OWN_INCONCLUSIVE=0, OWN_CONFIRMED=1, OWN_INCOMPATIBLE=2 };
bool g_uncertain=false;
ulong g_event_serial=0;
int g_diagnostic_count=0,g_ownership_count=0,g_window_ticks=0;
bool g_diagnostic_capped=false,g_ownership_capped=false;
bool g_ownership_failure_capped=false;
int g_ownership_failure_count=0,g_final_details=0;
ulong g_ownership_success_suppressed=0,g_ownership_failure_suppressed=0;
bool g_ownership_verbose=false,g_ownership_recovery=false;
ulong g_ownership_context=0;
struct OwnershipTrace
{
   ulong ticket;
   bool confirmed;
   OwnershipState state;
   ulong position_id;
   double volume;
   double entry;
   double sl;
   double tp;
};
OwnershipTrace g_ownership_trace[];
double g_equity_high=0,g_equity_low=0,g_logged_high=0,g_logged_low=0;
ulong g_known_orders[];
ulong g_signal_count=0,g_entry_requests=0,g_own_deals=0,g_exit_deals=0,g_sl_exits=0,g_tp_exits=0;

CTrade g_trade;
int g_fast = INVALID_HANDLE, g_slow = INVALID_HANDLE;
datetime g_bar = 0;
bool g_busy = false, g_auditing = false, g_halted = false;
bool g_foreign_alert = false;
ulong g_last_order = 0, g_last_deal = 0;
double g_requested_price = 0;
ENUM_ORDER_TYPE g_requested_side = ORDER_TYPE_BUY;
struct PositionTrack
{
   ulong id;
   ulong ticket;
   ulong origin_order;
   ulong origin_deal;
   bool repair_used;
   bool close_used;
   bool ownership_alert;
   OwnershipState ownership;
   int inconclusive_attempts;
   ulong last_attempt_event;
   bool reconcile_exhausted;
   double logged_volume;
   double logged_entry;
   double logged_sl;
   double logged_tp;
};
PositionTrack g_positions[];
ulong g_cancel_attempts[];

void LogBlock(const string reason) { Print("MT5SF001: entrada bloqueada: ", reason); }
void Halt(const string reason)
{
   if(!g_halted) Print("MT5SF001 CRITICO: ", reason, ". Novas entradas bloqueadas.");
   g_halted = true;
}

bool IsTester() { return (bool)MQLInfoInteger(MQL_TESTER); }
bool IsNetting()
{
   return AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
}

int Track(const ulong id, const ulong ticket)
{
   for(int i=0; i<ArraySize(g_positions); ++i)
      if(g_positions[i].id==id) { g_positions[i].ticket=ticket; return i; }
   int n=ArraySize(g_positions);
   if(ArrayResize(g_positions,n+1)!=n+1) { Halt("memoria de rastreamento indisponivel"); return -1; }
   g_positions[n].id=id;
   g_positions[n].ticket=ticket;
   g_positions[n].origin_order=0;
   g_positions[n].origin_deal=0;
   g_positions[n].repair_used=false;
   g_positions[n].close_used=false;
   g_positions[n].ownership_alert=false;
   g_positions[n].ownership=OWN_INCONCLUSIVE;
   g_positions[n].inconclusive_attempts=0;
   g_positions[n].last_attempt_event=0;
   g_positions[n].reconcile_exhausted=false;
   g_positions[n].logged_volume=-1;
   g_positions[n].logged_entry=0;
   g_positions[n].logged_sl=0;
   g_positions[n].logged_tp=0;
   return n;
}


// Markers exist only in the Strategy Tester's emulated global-variable store,
// not in live terminal globals. Reinitialization never clears them.
// If persistence fails, deny the operation. Collisions fail closed.
// A wholly new Tester environment may reset markers; history/ownership is still
// reconstructed and no state from a previous independent run is assumed.
bool ConsumeBudget(const string kind,const ulong id)
{
   if(!IsTester() || id==0) return false;
   string key=StringFormat("MT5SF110.%I64u.%I64u.%s",InpMagic,id,kind);
   if(GlobalVariableCheck(key)) return false;
   if(GlobalVariableSet(key,1.0)==0)
   {
      Halt("nao foi possivel registrar limite de recuperacao");
      return false;
   }
   return true;
}

bool FOKAllowed()
{
   return (SymbolInfoInteger(InpSymbol,SYMBOL_FILLING_MODE)&SYMBOL_FILLING_FOK)!=0;
}

bool HasForeignOrder()
{
   for(int i=OrdersTotal()-1;i>=0;--i)
   {
      if(OrderGetTicket(i)==0) return true;
      if(OrderGetString(ORDER_SYMBOL)==InpSymbol &&
         (ulong)OrderGetInteger(ORDER_MAGIC)!=InpMagic) return true;
   }
   return false;
}


string OwnershipName(const OwnershipState state)
{
   if(state==OWN_CONFIRMED) return "CONFIRMED";
   if(state==OWN_INCOMPATIBLE) return "INCOMPATIBLE";
   return "INCONCLUSIVE";
}

// This gate runs BEFORE StringFormat. It controls printing only.
// Independent failure budget cannot be consumed by successful repeated queries.
// Mandatory Halt()/trade-result messages remain outside both diagnostic caps.
bool OwnershipAllows(const bool important=false,const bool force_success=false)
{
   if(important)
   {
      if(g_ownership_failure_count<InpOwnershipFailureMaxRecords)
      { g_ownership_failure_count++; return true; }
      g_ownership_failure_suppressed++;
      if(!g_ownership_failure_capped)
      {
         Print("MT5SF001 OWN: reserva de falhas atingida; contagem e protecoes continuam.");
         g_ownership_failure_capped=true;
      }
      return false;
   }
   if(!InpDiagnosticEnabled || (!g_ownership_verbose && !force_success))
   { g_ownership_success_suppressed++; return false; }
   if(g_ownership_count>=InpOwnershipMaxRecords)
   {
      g_ownership_success_suppressed++;
      if(!g_ownership_capped)
      {
         Print("MT5SF001 OWN: limite de sucessos atingido; reserva de falhas preservada.");
         g_ownership_capped=true;
      }
      return false;
   }
   g_ownership_count++;
   return true;
}

void OwnershipLog(const string text)
{
   PrintFormat("MT5SF001 OWN event=%I64u context_ticket=%I64u %s",
               g_event_serial,g_ownership_context,text);
}

void Diagnostic(const string label)
{
   if(!InpDiagnosticEnabled || !IsTester()) return;
   if(g_diagnostic_count>=InpDiagnosticMaxRecords)
   {
      if(!g_diagnostic_capped)
      {
         Print("MT5SF001 DIAG: limite atingido; protecoes continuam ativas.");
         g_diagnostic_capped=true;
      }
      return;
   }
   g_diagnostic_count++;
   MqlTick tick={};
   ResetLastError();
   bool ok=SymbolInfoTick(InpSymbol,tick);
   int error=GetLastError();
   PrintFormat("MT5SF001 DIAG tag=%s event=%I64u sim_time=%s tick_msc=%I64d tick_ok=%s tick_error=%d bid=%.8f ask=%.8f last=%.8f flags=%u tick_volume=%I64u tick_volume_real=%.8f balance=%.8f equity=%.8f eq_high=%.8f eq_low=%.8f halted=%s uncertain=%s",
               label,g_event_serial,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
               tick.time_msc,ok?"true":"false",error,tick.bid,tick.ask,tick.last,
               tick.flags,tick.volume,tick.volume_real,AccountInfoDouble(ACCOUNT_BALANCE),
               AccountInfoDouble(ACCOUNT_EQUITY),g_equity_high,g_equity_low,
               g_halted?"true":"false",g_uncertain?"true":"false");
}

void ObserveEquity()
{
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   if(!MathIsValidNumber(equity)) { Halt("equity invalida"); return; }
   if(g_equity_high==0 && g_equity_low==0)
   {
      g_equity_high=equity; g_equity_low=equity;
      g_logged_high=equity; g_logged_low=equity;
      Diagnostic("EQUITY_BASELINE");
      return;
   }
   if(equity>g_equity_high) g_equity_high=equity;
   if(equity<g_equity_low) g_equity_low=equity;
   if(g_equity_high-g_logged_high>=InpEquityExtremeStep)
   { g_logged_high=g_equity_high; Diagnostic("EQUITY_NEW_HIGH"); }
   if(g_logged_low-g_equity_low>=InpEquityExtremeStep)
   { g_logged_low=g_equity_low; Diagnostic("EQUITY_NEW_LOW"); }
}

void RememberOrder(const ulong ticket)
{
   if(ticket==0) return;
   for(int i=0;i<ArraySize(g_known_orders);++i) if(g_known_orders[i]==ticket) return;
   int n=ArraySize(g_known_orders);
   if(ArrayResize(g_known_orders,n+1)!=n+1) { Halt("memoria de ordens indisponivel"); return; }
   g_known_orders[n]=ticket;
}
bool KnownOrder(const ulong ticket)
{
   for(int i=0;i<ArraySize(g_known_orders);++i) if(g_known_orders[i]==ticket) return true;
   return false;
}

// Use bool-return overloads and ResetLastError for EVERY ownership property.
// Zero/empty is never treated as an unavailable query without inspecting success.
bool HDI(const ulong ticket,const ENUM_DEAL_PROPERTY_INTEGER prop,long &value)
{
   ResetLastError(); bool ok=HistoryDealGetInteger(ticket,prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=deal.int ticket=%I64u prop=%s ok=%s error=%d value=%I64d",
                ticket,EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
bool HDS(const ulong ticket,const ENUM_DEAL_PROPERTY_STRING prop,string &value)
{
   ResetLastError(); bool ok=HistoryDealGetString(ticket,prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=deal.string ticket=%I64u prop=%s ok=%s error=%d value=%s",
                ticket,EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
bool HDD(const ulong ticket,const ENUM_DEAL_PROPERTY_DOUBLE prop,double &value)
{
   ResetLastError(); bool ok=HistoryDealGetDouble(ticket,prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=deal.double ticket=%I64u prop=%s ok=%s error=%d value=%.8f",
                ticket,EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
bool HOI(const ulong ticket,const ENUM_ORDER_PROPERTY_INTEGER prop,long &value)
{
   ResetLastError(); bool ok=HistoryOrderGetInteger(ticket,prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=history_order.int ticket=%I64u prop=%s ok=%s error=%d value=%I64d",
                ticket,EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
bool HOS(const ulong ticket,const ENUM_ORDER_PROPERTY_STRING prop,string &value)
{
   ResetLastError(); bool ok=HistoryOrderGetString(ticket,prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=history_order.string ticket=%I64u prop=%s ok=%s error=%d value=%s",
                ticket,EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
bool PI(const ENUM_POSITION_PROPERTY_INTEGER prop,long &value)
{
   ResetLastError(); bool ok=PositionGetInteger(prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=position.int prop=%s ok=%s error=%d value=%I64d",
                EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
bool PS(const ENUM_POSITION_PROPERTY_STRING prop,string &value)
{
   ResetLastError(); bool ok=PositionGetString(prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=position.string prop=%s ok=%s error=%d value=%s",
                EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
bool PD(const ENUM_POSITION_PROPERTY_DOUBLE prop,double &value)
{
   ResetLastError(); bool ok=PositionGetDouble(prop,value); int err=GetLastError();
   if(OwnershipAllows(!ok || err!=0)) OwnershipLog(StringFormat("query=position.double prop=%s ok=%s error=%d value=%.8f",
                EnumToString(prop),ok?"true":"false",err,value));
   return ok;
}
void CompareText(const string field,const string actual,const string expected)
{
   if(OwnershipAllows(actual!=expected)) OwnershipLog(StringFormat("compare=%s actual=%s expected=%s match=%s",
                field,actual,expected,actual==expected?"true":"false"));
}
void CompareId(const string field,const ulong actual,const ulong expected)
{
   if(OwnershipAllows(actual!=expected)) OwnershipLog(StringFormat("compare=%s actual=%I64u expected=%I64u match=%s",
                field,actual,expected,actual==expected?"true":"false"));
}

// Local snapshots keep enumeration separate from per-deal validation.
// No HistoryOrderSelect/HistoryDealSelect is used inside this proof.
struct OwnershipOrderSnapshot
{
   ulong enumerated_ticket;
   long reported_ticket;
   long magic;
   long position_id;
   long state;
   string symbol;
};

// Capture all position/deal/order fields separately; no combined opaque OR.
// A successful contradictory read means INCOMPATIBLE. A failed read, zero
// linkage or a changing snapshot means INCONCLUSIVE, not mixed ownership.
OwnershipState ProveOwnershipCore(const ulong ticket,ulong &id,ulong &first_order,
                              ulong &first_deal,string &why)
{
   id=0; first_order=0; first_deal=0;
   ResetLastError();
   bool selected=PositionSelectByTicket(ticket); int err=GetLastError();
   if(OwnershipAllows(!selected || err!=0)) OwnershipLog(StringFormat("query=PositionSelectByTicket ticket=%I64u ok=%s error=%d",
                ticket,selected?"true":"false",err));
   if(!selected) { why="position.select unavailable"; return OWN_INCONCLUSIVE; }
   string symbol="";
   long magic=0,identifier=0,type=0,current_ticket=0;
   double live_volume=0;
   bool reads=PS(POSITION_SYMBOL,symbol);
   if(!PI(POSITION_MAGIC,magic)) reads=false;
   if(!PI(POSITION_IDENTIFIER,identifier)) reads=false;
   if(!PI(POSITION_TICKET,current_ticket)) reads=false;
   if(!PI(POSITION_TYPE,type)) reads=false;
   if(!PD(POSITION_VOLUME,live_volume)) reads=false;
   if(!reads) { why="position property query failed"; return OWN_INCONCLUSIVE; }
   id=(ulong)identifier;
   CompareText("position.symbol",symbol,InpSymbol);
   CompareId("position.magic",(ulong)magic,InpMagic);
   CompareId("position.ticket",(ulong)current_ticket,ticket);
   if(symbol!=InpSymbol || (ulong)magic!=InpMagic)
   { why="position symbol/magic incompatible"; return OWN_INCOMPATIBLE; }
   if(id==0 || (ulong)current_ticket!=ticket || live_volume<=0 ||
      !MathIsValidNumber(live_volume))
   { why="position linkage/snapshot unavailable"; return OWN_INCONCLUSIVE; }
   if(type!=POSITION_TYPE_BUY && type!=POSITION_TYPE_SELL)
   { why="position type unavailable"; return OWN_INCONCLUSIVE; }
   if(IsNetting() && HasForeignOrder())
   { why="netting with foreign or unreadable active order"; return OWN_INCONCLUSIVE; }
   ResetLastError();
   bool history=HistorySelectByPosition(id); err=GetLastError();
   int deals=HistoryDealsTotal(),orders=HistoryOrdersTotal();
   if(OwnershipAllows(!history || err!=0 || deals==0 || orders==0)) OwnershipLog(StringFormat("query=HistorySelectByPosition id=%I64u ok=%s error=%d deals=%d orders=%d",
                id,history?"true":"false",err,deals,orders));
   if(!history) { why="position history selection failed"; return OWN_INCONCLUSIVE; }
   if(orders<=0) { why="position order history empty"; return OWN_INCONCLUSIVE; }

   // Enumerate the actual order list BEFORE reading any deal. Cache the ticket
   // and every relevant property while that indexed order is available.
   // A count alone does not prove that DEAL_ORDER belongs to this selection.
   OwnershipOrderSnapshot order_snapshot[];
   if(ArrayResize(order_snapshot,orders)!=orders)
   { why="cannot allocate historical order snapshot"; return OWN_INCONCLUSIVE; }
   bool order_snapshot_ok=true;
   for(int j=0;j<orders;++j)
   {
      ResetLastError();
      ulong enumerated=HistoryOrderGetTicket(j);
      int enumeration_error=GetLastError();
      order_snapshot[j].enumerated_ticket=enumerated;
      order_snapshot[j].reported_ticket=0;
      order_snapshot[j].magic=0;
      order_snapshot[j].position_id=0;
      order_snapshot[j].state=0;
      order_snapshot[j].symbol="";
      if(OwnershipAllows(enumerated==0 || enumeration_error!=0)) OwnershipLog(StringFormat("query=HistoryOrderGetTicket index=%d ticket=%I64u nonzero=%s error=%d expected_position_id=%I64u",
                   j,enumerated,enumerated!=0?"true":"false",enumeration_error,id));
      if(enumerated==0 || enumeration_error!=0)
      { order_snapshot_ok=false; continue; }

      bool properties_ok=HOI(enumerated,ORDER_TICKET,order_snapshot[j].reported_ticket);
      if(!HOI(enumerated,ORDER_MAGIC,order_snapshot[j].magic)) properties_ok=false;
      if(!HOS(enumerated,ORDER_SYMBOL,order_snapshot[j].symbol)) properties_ok=false;
      if(!HOI(enumerated,ORDER_POSITION_ID,order_snapshot[j].position_id)) properties_ok=false;
      if(!HOI(enumerated,ORDER_STATE,order_snapshot[j].state)) properties_ok=false;
      CompareId("enumerated_order.reported_ticket",
                (ulong)order_snapshot[j].reported_ticket,enumerated);
      if(OwnershipAllows(!properties_ok)) OwnershipLog(StringFormat("order_snapshot index=%d ticket=%I64u properties_ok=%s reported_ticket=%I64d magic=%I64d symbol=%s position_id=%I64d state=%I64d",
                   j,enumerated,properties_ok?"true":"false",
                   order_snapshot[j].reported_ticket,order_snapshot[j].magic,
                   order_snapshot[j].symbol,order_snapshot[j].position_id,
                   order_snapshot[j].state));
      if(!properties_ok || order_snapshot[j].reported_ticket==0 ||
         (ulong)order_snapshot[j].reported_ticket!=enumerated)
         order_snapshot_ok=false;
      for(int k=0;k<j;++k)
         if(order_snapshot[k].enumerated_ticket==enumerated)
            order_snapshot_ok=false;
   }
   // Property reads should not change either list. If the counts changed,
   // preserve the uncertainty rather than validating against mixed snapshots.
   int orders_after=HistoryOrdersTotal(),deals_after=HistoryDealsTotal();
   if(OwnershipAllows(!order_snapshot_ok || orders_after!=orders || deals_after!=deals)) OwnershipLog(StringFormat("order_snapshot orders_before=%d orders_after=%d deals_before=%d deals_after=%d complete=%s",
                orders,orders_after,deals,deals_after,order_snapshot_ok?"true":"false"));
   if(!order_snapshot_ok || orders_after!=orders || deals_after!=deals)
   { why="historical order enumeration/property snapshot inconclusive"; return OWN_INCONCLUSIVE; }
   if(deals==0) { why="position deal history empty"; return OWN_INCONCLUSIVE; }
   double signed_volume=0;
   int count=0;
   for(int i=0;i<deals;++i)
   {
      ResetLastError();
      ulong deal=HistoryDealGetTicket(i); err=GetLastError();
      if(OwnershipAllows(deal==0 || err!=0)) OwnershipLog(StringFormat("query=HistoryDealGetTicket index=%d ticket=%I64u error=%d",i,deal,err));
      if(deal==0) { why="deal ticket unavailable"; return OWN_INCONCLUSIVE; }
      long deal_type=0;
      if(!HDI(deal,DEAL_TYPE,deal_type)) { why="deal.type query failed"; return OWN_INCONCLUSIVE; }
      if(deal_type!=DEAL_TYPE_BUY && deal_type!=DEAL_TYPE_SELL) continue;
      string deal_symbol="",order_symbol="";
      long deal_magic=0,deal_id=0,order=0,entry=0,order_magic=0,order_id=0,order_state=0,order_ticket=0;
      double volume=0;
      reads=HDS(deal,DEAL_SYMBOL,deal_symbol);
      if(!HDI(deal,DEAL_MAGIC,deal_magic)) reads=false;
      if(!HDI(deal,DEAL_POSITION_ID,deal_id)) reads=false;
      if(!HDI(deal,DEAL_ORDER,order)) reads=false;
      if(!HDI(deal,DEAL_ENTRY,entry)) reads=false;
      if(!HDD(deal,DEAL_VOLUME,volume)) reads=false;
      if(!reads) { why="deal property query failed"; return OWN_INCONCLUSIVE; }
      CompareText("deal.symbol",deal_symbol,InpSymbol);
      CompareId("deal.magic",(ulong)deal_magic,InpMagic);
      CompareId("deal.position_id",(ulong)deal_id,id);
      if(OwnershipAllows(order==0)) OwnershipLog(StringFormat("compare=deal.order nonzero=%s value=%I64d",order!=0?"true":"false",order));
      if(deal_symbol!=InpSymbol || (ulong)deal_magic!=InpMagic ||
         (deal_id!=0 && (ulong)deal_id!=id))
      { why="deal symbol/magic/position_id incompatible"; return OWN_INCOMPATIBLE; }
      if(deal_id==0 || order==0 || volume<=0 || !MathIsValidNumber(volume))
      { why="deal linkage/volume inconclusive"; return OWN_INCONCLUSIVE; }
      // Match the actual DEAL_ORDER, never the deal ticket, position identifier
      // or first enumerated order. No individual selection alters the lists.
      int matched=-1,matches=0;
      for(int j=0;j<orders;++j)
      {
         bool exact=order_snapshot[j].enumerated_ticket==(ulong)order;
         if(OwnershipAllows(false)) OwnershipLog(StringFormat("compare=DEAL_ORDER_vs_enumeration deal=%I64u expected_order=%I64d index=%d enumerated_ticket=%I64u match=%s",
                      deal,order,j,order_snapshot[j].enumerated_ticket,exact?"true":"false"));
         if(exact) { matched=j; matches++; }
      }
      if(matches!=1 || matched<0)
      { why="DEAL_ORDER lacks unique exact enumerated match"; return OWN_INCONCLUSIVE; }
      order_magic=order_snapshot[matched].magic;
      order_symbol=order_snapshot[matched].symbol;
      order_id=order_snapshot[matched].position_id;
      order_state=order_snapshot[matched].state;
      order_ticket=order_snapshot[matched].reported_ticket;
      CompareId("history_order.ticket",(ulong)order_ticket,(ulong)order);
      CompareId("history_order.magic",(ulong)order_magic,InpMagic);
      CompareText("history_order.symbol",order_symbol,InpSymbol);
      CompareId("history_order.position_id",(ulong)order_id,id);
      // An order not yet finalized or with zero linkage is not proof of mixing.
      if(order_ticket==0 || order_id==0 || order_symbol=="" ||
         (order_state!=ORDER_STATE_FILLED && order_state!=ORDER_STATE_CANCELED))
      { why="historical order linkage/state not finalized"; return OWN_INCONCLUSIVE; }
      if((ulong)order_ticket!=(ulong)order || (ulong)order_id!=id)
      { why="historical order/deal/position linkage inconsistent"; return OWN_INCONCLUSIVE; }
      if((ulong)order_magic!=InpMagic || order_symbol!=InpSymbol)
      { why="historical order symbol/magic incompatible"; return OWN_INCOMPATIBLE; }
      if(count==0)
      {
         if(entry!=DEAL_ENTRY_IN)
         { why="history does not establish initial entry"; return OWN_INCONCLUSIVE; }
         first_deal=deal; first_order=(ulong)order;
      }
      signed_volume+=(deal_type==DEAL_TYPE_BUY?volume:-volume);
      count++;
   }
   double expected=(type==POSITION_TYPE_BUY?live_volume:-live_volume);
   double step=SymbolInfoDouble(InpSymbol,SYMBOL_VOLUME_STEP);
   if(OwnershipAllows(count==0 || MathAbs(signed_volume-expected)>MathMax(1e-8,step*1e-6))) OwnershipLog(StringFormat("compare=signed_volume actual=%.8f expected=%.8f count=%d",
                signed_volume,expected,count));
   if(count==0 || MathAbs(signed_volume-expected)>MathMax(1e-8,step*1e-6))
   { why="history/live volume snapshot not reconciled"; return OWN_INCONCLUSIVE; }
   if(!PositionSelectByTicket(ticket))
   { why="position disappeared during proof"; return OWN_INCONCLUSIVE; }
   long final_id=0,final_magic=0,final_type=0;
   double final_volume=0;
   reads=PI(POSITION_IDENTIFIER,final_id);
   if(!PI(POSITION_MAGIC,final_magic)) reads=false;
   if(!PI(POSITION_TYPE,final_type)) reads=false;
   if(!PD(POSITION_VOLUME,final_volume)) reads=false;
   if(!reads || (ulong)final_id!=id || (ulong)final_magic!=InpMagic ||
      final_type!=type || MathAbs(final_volume-live_volume)>1e-8)
   { why="position changed during proof"; return OWN_INCONCLUSIVE; }
   why="complete history and current exposure reconciled";
   return OWN_CONFIRMED;
}


// Logging metadata only. No memoized ownership result is ever used for safety:
// ProveOwnershipCore executes in FULL on EVERY invocation.
OwnershipState ProveOwnership(const ulong ticket,ulong &id,ulong &first_order,
                              ulong &first_deal,string &why)
{
   int slot=-1;
   for(int i=0;i<ArraySize(g_ownership_trace);++i)
      if(g_ownership_trace[i].ticket==ticket) { slot=i; break; }
   if(slot<0)
   {
      int n=ArraySize(g_ownership_trace);
      if(ArrayResize(g_ownership_trace,n+1)==n+1)
      {
         slot=n;
         g_ownership_trace[n].ticket=ticket;
         g_ownership_trace[n].confirmed=false;
         g_ownership_trace[n].state=OWN_INCONCLUSIVE;
         g_ownership_trace[n].position_id=0;
         g_ownership_trace[n].volume=0;
         g_ownership_trace[n].entry=0;
         g_ownership_trace[n].sl=0;
         g_ownership_trace[n].tp=0;
      }
   }
   // Raw metadata comparison avoids formatting a diagnostic on every tick.
   ulong observed_id=0;
   double observed_volume=0,observed_entry=0,observed_sl=0,observed_tp=0;
   bool observed=PositionSelectByTicket(ticket);
   if(observed)
   {
      observed_id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      observed_volume=PositionGetDouble(POSITION_VOLUME);
      observed_entry=PositionGetDouble(POSITION_PRICE_OPEN);
      observed_sl=PositionGetDouble(POSITION_SL);
      observed_tp=PositionGetDouble(POSITION_TP);
   }
   bool first=(slot<0 || !g_ownership_trace[slot].confirmed);
   bool changed=(slot<0 || !observed || observed_id!=g_ownership_trace[slot].position_id ||
                 observed_volume!=g_ownership_trace[slot].volume ||
                 observed_entry!=g_ownership_trace[slot].entry ||
                 observed_sl!=g_ownership_trace[slot].sl || observed_tp!=g_ownership_trace[slot].tp);
   OwnershipState previous=slot<0?OWN_INCONCLUSIVE:g_ownership_trace[slot].state;
   bool previous_verbose=g_ownership_verbose;
   ulong previous_context=g_ownership_context;
   g_ownership_context=ticket;
   g_ownership_verbose=first || changed || previous!=OWN_CONFIRMED || g_ownership_recovery;

   OwnershipState state=ProveOwnershipCore(ticket,id,first_order,first_deal,why);
   if(state!=previous || first || changed || g_ownership_recovery)
   {
      if(OwnershipAllows(state!=OWN_CONFIRMED,true))
         OwnershipLog(StringFormat("proof_result state=%s previous=%s id=%I64u first=%s changed=%s recovery=%s reason=%s",
                      OwnershipName(state),OwnershipName(previous),id,first?"true":"false",
                      changed?"true":"false",g_ownership_recovery?"true":"false",why));
   }
   if(slot>=0)
   {
      g_ownership_trace[slot].state=state;
      g_ownership_trace[slot].position_id=observed_id;
      g_ownership_trace[slot].volume=observed_volume;
      g_ownership_trace[slot].entry=observed_entry;
      g_ownership_trace[slot].sl=observed_sl;
      g_ownership_trace[slot].tp=observed_tp;
      if(state==OWN_CONFIRMED) g_ownership_trace[slot].confirmed=true;
   }
   g_ownership_verbose=previous_verbose;
   g_ownership_context=previous_context;
   return state;
}

// Input volume is SHARES. MQL5 trade volume is in symbol lots/contracts.
// PETR4 normally has contract_size=1: 100 shares -> volume 100.
// Conversion is explicit and never rounds volume up or changes the share count.
bool GetVolume(double &volume, string &reason)
{
   double contract = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double minimum = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   double maximum = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   double limit = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_LIMIT);
   if(contract <= 0 || minimum <= 0 || maximum < minimum || step <= 0)
   {
      reason = "propriedades de volume invalidas";
      return false;
   }
   volume = InpShares / contract;
   double units = volume / step;
   double eps = 1e-8 * MathMax(1.0, MathAbs(units));
   if(!MathIsValidNumber(volume) || volume < minimum - 1e-9 ||
      volume > maximum + 1e-9 || MathAbs(units - MathRound(units)) > eps ||
      (limit > 0 && volume > limit + 1e-9))
   {
      reason = StringFormat("volume %.8f incompativel: min=%.8f max=%.8f step=%.8f limit=%.8f",
                            volume, minimum, maximum, step, limit);
      return false;
   }
   // Remove floating point noise only after validating the original share count.
   volume = NormalizeDouble(MathRound(units) * step, 8);
   return true;
}

// Block all exposure on the symbol, including other magic numbers.
// Never close, modify or cancel anything. This also prevents netting merges.
// Fail closed if a ticket cannot be inspected reliably.
bool HasExposure()
{
   for(int i = PositionsTotal() - 1; i >= 0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) return true;
      if(PositionGetString(POSITION_SYMBOL) == InpSymbol) return true;
   }
   for(int i = OrdersTotal() - 1; i >= 0; --i)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0) return true;
      if(OrderGetString(ORDER_SYMBOL) == InpSymbol) return true;
   }
   return false;
}


bool Permissions(const ENUM_ORDER_TYPE side, string &reason)
{
   if(!MQLInfoInteger(MQL_TESTER) ||
      !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {
      reason = "ambiente Tester ou permissao de negociacao indisponivel";
      return false;
   }
   long mode = SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED || mode == SYMBOL_TRADE_MODE_CLOSEONLY ||
      (side == ORDER_TYPE_BUY && mode == SYMBOL_TRADE_MODE_SHORTONLY) ||
      (side == ORDER_TYPE_SELL && mode == SYMBOL_TRADE_MODE_LONGONLY))
   {
      reason = "direcao proibida pelo simbolo";
      return false;
   }
   long flags = SymbolInfoInteger(InpSymbol, SYMBOL_ORDER_MODE);
   if((flags & SYMBOL_ORDER_MARKET) == 0 ||
      (flags & SYMBOL_ORDER_SL) == 0 || (flags & SYMBOL_ORDER_TP) == 0)
   {
      reason = "simbolo nao permite entrada a mercado com SL e TP";
      return false;
   }
   return true;
}

double TickFloor(const double price, const double tick, const int digits)
{
   return NormalizeDouble(MathFloor(price / tick + 1e-9) * tick, digits);
}

double TickCeil(const double price, const double tick, const int digits)
{
   return NormalizeDouble(MathCeil(price / tick - 1e-9) * tick, digits);
}

// Round stop loss TOWARD entry (do not intentionally exceed percentage risk).
// Round take profit toward entry too. Both levels must remain valid after rounding.
// Minimum stops are measured from current Bid for buys and Ask for sells.
// Never widen stops to satisfy a broker restriction: discard that signal instead.
bool BuildStops(const ENUM_ORDER_TYPE side, const MqlTick &quote,
                double &price, double &sl, double &tp, string &reason)
{
   double tick = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_SIZE);
   double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   if(tick <= 0 || point <= 0 || quote.bid <= 0 || quote.ask < quote.bid ||
      !MathIsValidNumber(quote.bid) || !MathIsValidNumber(quote.ask))
   {
      reason = "cotacao ou tick size invalido";
      return false;
   }
   price = side == ORDER_TYPE_BUY ? quote.ask : quote.bid;
   if(MathAbs(price / tick - MathRound(price / tick)) > 1e-6)
   {
      reason = "preco de entrada fora da grade de ticks";
      return false;
   }
   double loss = InpStopLossPercent / 100.0;
   double gain = InpTakeProfitPercent / 100.0;
   double distance = (double)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL) * point;
   double eps = tick * 1e-6;
   if(side == ORDER_TYPE_BUY)
   {
      sl = TickCeil(price * (1.0 - loss), tick, digits);
      tp = TickFloor(price * (1.0 + gain), tick, digits);
      if(sl <= 0 || sl >= quote.bid || tp <= quote.ask ||
         quote.bid - sl + eps < distance || tp - quote.bid + eps < distance)
      {
         reason = "SL/TP de compra invalidos ou menores que stops_level";
         return false;
      }
   }
   else
   {
      sl = TickFloor(price * (1.0 + loss), tick, digits);
      tp = TickCeil(price * (1.0 - gain), tick, digits);
      if(tp <= 0 || tp >= quote.bid || sl <= quote.ask ||
         sl - quote.ask + eps < distance || quote.ask - tp + eps < distance)
      {
         reason = "SL/TP de venda invalidos ou menores que stops_level";
         return false;
      }
   }
   return true;
}


bool ReadSignal(int &signal)
{
   signal = 0;
   if(BarsCalculated(g_fast) < InpSlowPeriod + 3 ||
      BarsCalculated(g_slow) < InpSlowPeriod + 3) return false;
   double fast[2], slow[2];
   // CopyBuffer stores oldest first: [0] is shift 2, [1] is shift 1.
   if(CopyBuffer(g_fast, 0, 1, 2, fast) != 2 ||
      CopyBuffer(g_slow, 0, 1, 2, slow) != 2) return false;
   for(int i = 0; i < 2; ++i)
      if(fast[i] == EMPTY_VALUE || slow[i] == EMPTY_VALUE ||
         !MathIsValidNumber(fast[i]) || !MathIsValidNumber(slow[i])) return false;
   if(fast[0] <= slow[0] && fast[1] > slow[1]) signal = 1;
   else if(fast[0] >= slow[0] && fast[1] < slow[1]) signal = -1;
   return true;
}


// Return values are inspected for every request. Check success does not guarantee
// fill; the state is always re-read. No recovery is sent outside Strategy Tester.
bool CheckRequest(MqlTradeRequest &request)
{
   if(!IsTester()) return false;
   MqlTradeCheckResult check={};
   ResetLastError();
   bool ok=OrderCheck(request,check);
   PrintFormat("MT5SF001 CHECK action=%d position=%I64u order=%I64u ok=%s code=%u error=%d comment=%s",
               (int)request.action,request.position,request.order,
               ok?"true":"false",check.retcode,GetLastError(),check.comment);
   return ok && (check.retcode==0 || check.retcode==TRADE_RETCODE_DONE);
}

bool SendRecovery(MqlTradeRequest &request)
{
   if(!IsTester() || g_busy || g_uncertain) return false;
   g_busy=true;
   MqlTradeResult result={};
   ResetLastError();
   bool ok=OrderSend(request,result);
   g_busy=false;
   PrintFormat("MT5SF001 RECOVERY action=%d position=%I64u requested=%.8f executed=%.8f volume=%.8f SL=%.8f TP=%.8f order=%I64u deal=%I64u ok=%s code=%u error=%d comment=%s",
               (int)request.action,request.position,request.price,result.price,
               result.volume,request.sl,request.tp,result.order,result.deal,
               ok?"true":"false",result.retcode,GetLastError(),result.comment);
   if(result.order!=0) { g_last_order=result.order; RememberOrder(result.order); }
   if(result.deal!=0) g_last_deal=result.deal;
   return ok && result.retcode==TRADE_RETCODE_DONE;
}


struct OrderReconcile
{
   ulong ticket;
   int attempts;
   ulong event;
   bool exhausted;
};
OrderReconcile g_order_reconcile[];

int OrderSlot(const ulong ticket)
{
   for(int i=0;i<ArraySize(g_order_reconcile);++i)
      if(g_order_reconcile[i].ticket==ticket) return i;
   int n=ArraySize(g_order_reconcile);
   if(ArrayResize(g_order_reconcile,n+1)!=n+1) { Halt("memoria de reconciliacao indisponivel"); return -1; }
   g_order_reconcile[n].ticket=ticket; g_order_reconcile[n].attempts=0;
   g_order_reconcile[n].event=0; g_order_reconcile[n].exhausted=false;
   return n;
}

OwnershipState ProveActiveOrder(const ulong ticket)
{
   ResetLastError();
   bool selected=OrderSelect(ticket); int err=GetLastError();
   if(OwnershipAllows(!selected || err!=0)) OwnershipLog(StringFormat("query=OrderSelect ticket=%I64u ok=%s error=%d",ticket,selected?"true":"false",err));
   if(!selected) return OWN_INCONCLUSIVE;
   string symbol="";
   long magic=0,actual=0,pid=0;
   ResetLastError(); bool qs=OrderGetString(ORDER_SYMBOL,symbol); int es=GetLastError();
   ResetLastError(); bool qm=OrderGetInteger(ORDER_MAGIC,magic); int em=GetLastError();
   ResetLastError(); bool qt=OrderGetInteger(ORDER_TICKET,actual); int et=GetLastError();
   ResetLastError(); bool qp=OrderGetInteger(ORDER_POSITION_ID,pid); int ep=GetLastError();
   if(OwnershipAllows(!qs || es!=0)) OwnershipLog(StringFormat("query=active.symbol ok=%s error=%d value=%s",qs?"true":"false",es,symbol));
   if(OwnershipAllows(!qm || em!=0)) OwnershipLog(StringFormat("query=active.magic ok=%s error=%d value=%I64d",qm?"true":"false",em,magic));
   if(OwnershipAllows(!qt || et!=0)) OwnershipLog(StringFormat("query=active.ticket ok=%s error=%d value=%I64d",qt?"true":"false",et,actual));
   if(OwnershipAllows(!qp || ep!=0)) OwnershipLog(StringFormat("query=active.position_id ok=%s error=%d value=%I64d",qp?"true":"false",ep,pid));
   if(!qs || !qm || !qt || !qp) return OWN_INCONCLUSIVE;
   CompareText("active.symbol",symbol,InpSymbol);
   CompareId("active.magic",(ulong)magic,InpMagic);
   CompareId("active.ticket",(ulong)actual,ticket);
   if(symbol!=InpSymbol || (ulong)magic!=InpMagic) return OWN_INCOMPATIBLE;
   if((ulong)actual!=ticket) return OWN_INCONCLUSIVE;
   // A locally correlated request identifies this exact order, never another ticket.
   if(KnownOrder(ticket)) return OWN_CONFIRMED;
   // On restart, a linked live position must independently pass the full proof.
   if(pid!=0)
   {
      for(int i=PositionsTotal()-1;i>=0;--i)
      {
         ulong p=PositionGetTicket(i);
         if(p==0 || (ulong)PositionGetInteger(POSITION_IDENTIFIER)!=(ulong)pid) continue;
         ulong id,order,deal; string why;
         OwnershipState state=ProveOwnership(p,id,order,deal,why);
         if(state==OWN_CONFIRMED && id==(ulong)pid) return OWN_CONFIRMED;
         return state;
      }
   }
   return OWN_INCONCLUSIVE;
}

bool OwnActiveOrder(const ulong ticket)
{
   OwnershipState state=ProveActiveOrder(ticket);
   if(state==OWN_INCONCLUSIVE) g_uncertain=true;
   return state==OWN_CONFIRMED;
}

bool CancellationUsed(const ulong ticket)
{
   for(int i=0;i<ArraySize(g_cancel_attempts);++i)
      if(g_cancel_attempts[i]==ticket) return true;
   int n=ArraySize(g_cancel_attempts);
   if(ArrayResize(g_cancel_attempts,n+1)!=n+1)
   { Halt("memoria de cancelamentos indisponivel"); return true; }
   g_cancel_attempts[n]=ticket; // consume before any operation, including failed check
   return !ConsumeBudget("cancel",ticket);
}


void CancelOwnResiduals()
{
   ulong tickets[];
   for(int i=OrdersTotal()-1;i>=0;--i)
   {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0) { g_uncertain=true; continue; }
      string symbol=""; long magic=0;
      bool readable=OrderGetString(ORDER_SYMBOL,symbol);
      if(!OrderGetInteger(ORDER_MAGIC,magic)) readable=false;
      if(!readable) { g_uncertain=true; continue; }
      if(symbol!=InpSymbol || (ulong)magic!=InpMagic) continue;
      int n=ArraySize(tickets);
      if(ArrayResize(tickets,n+1)!=n+1) { Halt("memoria indisponivel"); return; }
      tickets[n]=ticket;
   }
   for(int i=0;i<ArraySize(tickets);++i)
   {
      ulong ticket=tickets[i];
      int slot=OrderSlot(ticket);
      if(slot<0) { g_uncertain=true; continue; }
      if(g_order_reconcile[slot].exhausted) { g_uncertain=true; continue; }
      if(g_order_reconcile[slot].event==g_event_serial)
      { g_uncertain=true; continue; }
      g_order_reconcile[slot].event=g_event_serial;
      OwnershipState state=ProveActiveOrder(ticket);
      if(OwnershipAllows(state!=OWN_CONFIRMED)) OwnershipLog(StringFormat("active_order=%I64u state=%s",ticket,OwnershipName(state)));
      if(state!=OWN_CONFIRMED)
      {
         g_uncertain=true;
         if(state==OWN_INCOMPATIBLE) Halt("ordem ativa comprovadamente incompativel; nao cancelar");
         else
         {
            g_order_reconcile[slot].attempts++;
            if(g_order_reconcile[slot].attempts>=InpReconcileMaxAttempts)
            {
               g_order_reconcile[slot].exhausted=true;
               Halt("reconciliacao de ordem esgotada; propriedade continua inconclusiva");
            }
         }
         continue;
      }
      Halt("saldo de ordem propria comprovada detectado");
      if(CancellationUsed(ticket) || !OwnActiveOrder(ticket)) continue;
      MqlTradeRequest request={};
      request.action=TRADE_ACTION_REMOVE; request.order=ticket;
      request.magic=InpMagic; request.symbol=InpSymbol; request.comment="MT5SF001_CANCEL";
      if(!CheckRequest(request) || !OwnActiveOrder(ticket)) continue;
      bool ok=SendRecovery(request);
      PrintFormat("MT5SF001 cancelamento order=%I64u confirmado=%s ainda_ativo=%s",
                  ticket,ok?"true":"false",OrderSelect(ticket)?"true":"false");
   }
}

bool HasOwnActiveOrder()
{
   // For closing, any unresolved order on the symbol is unsafe, even foreign.
   for(int i=OrdersTotal()-1;i>=0;--i)
   {
      if(OrderGetTicket(i)==0) return true;
      string symbol="";
      if(!OrderGetString(ORDER_SYMBOL,symbol)) return true;
      if(symbol==InpSymbol) return true;
   }
   return false;
}

// A stop is inadequate when absent, on the wrong side, off tick grid, or when
// nominal risk exceeds the configured distance (allow one tick rounding).
// A closer profitable stop is preserved; do not widen an existing protective SL.
// TP distance differences are logged but do not justify increasing position risk.
bool ProtectionAdequate(const ulong ticket)
{
   if(!PositionSelectByTicket(ticket)) return false;
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   double sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
   double tick=SymbolInfoDouble(InpSymbol,SYMBOL_TRADE_TICK_SIZE);
   bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
   if(!MathIsValidNumber(entry) || !MathIsValidNumber(sl) || !MathIsValidNumber(tp) ||
      entry<=0 || sl<=0 || tp<=0 || tick<=0) return false;
   if(MathAbs(sl/tick-MathRound(sl/tick))>1e-6 ||
      MathAbs(tp/tick-MathRound(tp/tick))>1e-6) return false;
   if((buy && (tp<=entry || sl>=tp)) || (!buy && (tp>=entry || sl<=tp))) return false;
   double risk=buy?entry-sl:sl-entry;
   return risk<=entry*InpStopLossPercent/100.0+tick+1e-8;
}

void LogPosition(const int index)
{
   ulong ticket=g_positions[index].ticket;
   if(!PositionSelectByTicket(ticket)) return;
   double volume=PositionGetDouble(POSITION_VOLUME);
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   double sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
   if(volume==g_positions[index].logged_volume && entry==g_positions[index].logged_entry &&
      sl==g_positions[index].logged_sl && tp==g_positions[index].logged_tp) return;
   bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
   double tick=SymbolInfoDouble(InpSymbol,SYMBOL_TRADE_TICK_SIZE);
   double risk=sl>0 && entry>0 ? 100.0*(buy?entry-sl:sl-entry)/entry : -1;
   double gain=tp>0 && entry>0 ? 100.0*(buy?tp-entry:entry-tp)/entry : -1;
   PrintFormat("MT5SF001 POSITION id=%I64u ticket=%I64u origin_order=%I64u origin_deal=%I64u volume=%.8f entry=%.8f SL=%.8f TP=%.8f nominal_SL=%.6f%% effective_SL_distance=%.6f%% effective_TP_distance=%.6f%% tick=%.8f",
               g_positions[index].id,ticket,g_positions[index].origin_order,
               g_positions[index].origin_deal,volume,entry,sl,tp,
               InpStopLossPercent,risk,gain,tick);
   Print("MT5SF001: distancia nominal nao garante perda realizada; gaps/slippage podem exceder o SL.");
   g_positions[index].logged_volume=volume;
   g_positions[index].logged_entry=entry;
   g_positions[index].logged_sl=sl;
   g_positions[index].logged_tp=tp;
}

bool BuildRepair(const ulong ticket, double &sl, double &tp, string &why)
{
   if(!PositionSelectByTicket(ticket)) return false;
   bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
   double entry=PositionGetDouble(POSITION_PRICE_OPEN);
   double old_sl=PositionGetDouble(POSITION_SL);
   MqlTick q={};
   double tick=SymbolInfoDouble(InpSymbol,SYMBOL_TRADE_TICK_SIZE);
   double point=SymbolInfoDouble(InpSymbol,SYMBOL_POINT);
   int digits=(int)SymbolInfoInteger(InpSymbol,SYMBOL_DIGITS);
   if(entry<=0 || tick<=0 || point<=0 || !SymbolInfoTick(InpSymbol,q) ||
      q.bid<=0 || q.ask<q.bid) { why="cotacao/propriedades indisponiveis"; return false; }
   double stops=(double)SymbolInfoInteger(InpSymbol,SYMBOL_TRADE_STOPS_LEVEL)*point;
   double freeze=(double)SymbolInfoInteger(InpSymbol,SYMBOL_TRADE_FREEZE_LEVEL)*point;
   double distance=MathMax(stops,freeze)+tick; // conservative, do not widen nominal risk
   if(buy)
   {
      sl=TickCeil(entry*(1-InpStopLossPercent/100.0),tick,digits);
      tp=TickFloor(entry*(1+InpTakeProfitPercent/100.0),tick,digits);
      if(old_sl>0 && old_sl<q.bid) sl=MathMax(sl,old_sl);
      if(sl<=0 || tp<=entry || q.bid-sl<distance || tp-q.bid<distance)
      { why="stops/freeze ou mercado ja ultrapassou niveis nominais"; return false; }
   }
   else
   {
      sl=TickFloor(entry*(1+InpStopLossPercent/100.0),tick,digits);
      tp=TickCeil(entry*(1-InpTakeProfitPercent/100.0),tick,digits);
      if(old_sl>q.ask) sl=MathMin(sl,old_sl);
      if(tp<=0 || tp>=entry || sl-q.ask<distance || q.ask-tp<distance)
      { why="stops/freeze ou mercado ja ultrapassou niveis nominais"; return false; }
   }
   return true;
}


bool SameOwner(const ulong ticket,const ulong expected_id)
{
   ulong id,order,deal; string why;
   OwnershipState state=ProveOwnership(ticket,id,order,deal,why);
   bool ok=state==OWN_CONFIRMED && id==expected_id;
   if(!ok)
   {
      g_uncertain=true;
      if(OwnershipAllows(true)) OwnershipLog(StringFormat("mutation_denied ticket=%I64u state=%s expected_id=%I64u actual_id=%I64u reason=%s",
                   ticket,OwnershipName(state),expected_id,id,why));
      if(state==OWN_INCOMPATIBLE || (state==OWN_CONFIRMED && id!=expected_id))
         Halt("propriedade mudou antes da mutacao");
   }
   return ok;
}

void RecoverPositionCore(const int index)
{
   if(g_uncertain) return; // never mutate while another unresolved snapshot is present
   ulong ticket=g_positions[index].ticket,id=g_positions[index].id;
   Halt("protecao propria inadequada; recuperacao limitada");
   if(!SameOwner(ticket,id)) return;
   if(!g_positions[index].repair_used && ConsumeBudget("repair",id))
   {
      g_positions[index].repair_used=true;
      double sl,tp; string why;
      MqlTradeRequest request={};
      request.action=TRADE_ACTION_SLTP;
      request.position=ticket;
      request.symbol=InpSymbol;
      request.magic=InpMagic;
      request.comment="MT5SF001_REPAIR";
      if(BuildRepair(ticket,sl,tp,why))
      {
         request.sl=sl; request.tp=tp;
         if(CheckRequest(request) && SameOwner(ticket,id))
         {
            bool ok=SendRecovery(request);
            PrintFormat("MT5SF001 reparo id=%I64u confirmado=%s",id,ok?"true":"false");
         }
      }
      else PrintFormat("MT5SF001 reparo inviavel id=%I64u motivo=%s",id,why);
   }
   if(!PositionSelectByTicket(ticket)) return; // already exited; NEVER reopen
   if(!SameOwner(ticket,id)) return;
   if(ProtectionAdequate(ticket)) { LogPosition(index); return; }
   if(g_positions[index].close_used || !ConsumeBudget("close",id)) return;
   g_positions[index].close_used=true;
   // Do not send another deal while a residual could fill and recreate exposure.
   if(HasOwnActiveOrder() || !FOKAllowed())
   {
      PrintFormat("MT5SF001 CRITICO: fechamento nao enviado id=%I64u: saldo ativo ou FOK indisponivel; revisao manual",id);
      return;
   }
   if(!SameOwner(ticket,id)) return;
   bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
   double volume=PositionGetDouble(POSITION_VOLUME);
   MqlTick q={};
   if(!SymbolInfoTick(InpSymbol,q) || q.bid<=0 || q.ask<q.bid)
   {
      PrintFormat("MT5SF001 CRITICO: sem cotacao para fechamento id=%I64u",id);
      return;
   }
   MqlTradeRequest request={};
   request.action=TRADE_ACTION_DEAL;
   request.position=ticket;
   request.symbol=InpSymbol;
   request.magic=InpMagic;
   request.volume=volume;
   request.type=buy?ORDER_TYPE_SELL:ORDER_TYPE_BUY;
   request.price=buy?q.bid:q.ask;
   request.deviation=InpDeviationPoints;
   request.type_filling=ORDER_FILLING_FOK;
   request.type_time=ORDER_TIME_GTC;
   request.comment="MT5SF001_CLOSE";
   if(CheckRequest(request) && SameOwner(ticket,id))
   {
      // Reread volume immediately before send to prevent an oversized close.
      if(MathAbs(PositionGetDouble(POSITION_VOLUME)-volume)>1e-8)
      { Print("MT5SF001 CRITICO: volume mudou; fechamento recusado."); return; }
      bool ok=SendRecovery(request);
      PrintFormat("MT5SF001 fechamento id=%I64u confirmado=%s ainda_aberta=%s; sem retry",
                  id,ok?"true":"false",PositionSelectByTicket(ticket)?"true":"false");
   }
   else PrintFormat("MT5SF001 CRITICO: fechamento recusado id=%I64u; sem retry",id);
}



void RecoverPosition(const int index)
{
   bool previous=g_ownership_recovery;
   g_ownership_recovery=true;
   if(OwnershipAllows(true))
      OwnershipLog(StringFormat("recovery_begin id=%I64u ticket=%I64u",
                   g_positions[index].id,g_positions[index].ticket));
   RecoverPositionCore(index);
   if(OwnershipAllows(true))
      OwnershipLog(StringFormat("recovery_end id=%I64u ticket=%I64u",
                   g_positions[index].id,g_positions[index].ticket));
   g_ownership_recovery=previous;
}

// Read-only reconciliation is bounded independently of recovery trade budgets.
// An incomplete snapshot does not set the permanent critical latch immediately.
// Exhaustion remains INCONCLUSIVE and fails closed, never reclassified as mixed.
void AuditExposure()
{
   if(!IsTester() || g_auditing || g_busy) return;
   g_auditing=true;
   g_uncertain=PendingDealsUnresolved();
   CancelOwnResiduals();
   ulong tickets[];
   for(int i=PositionsTotal()-1;i>=0;--i)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0) { g_uncertain=true; continue; }
      string symbol="";
      if(!PositionGetString(POSITION_SYMBOL,symbol)) { g_uncertain=true; continue; }
      if(symbol!=InpSymbol) continue;
      int n=ArraySize(tickets);
      if(ArrayResize(tickets,n+1)!=n+1) { Halt("memoria indisponivel"); break; }
      tickets[n]=ticket;
   }
   if(ArraySize(tickets)>1) Halt("mais de uma posicao no simbolo");
   for(int i=0;i<ArraySize(tickets);++i)
   {
      ulong ticket=tickets[i];
      if(!PositionSelectByTicket(ticket)) { g_uncertain=true; continue; }
      long identifier=0;
      if(!PositionGetInteger(POSITION_IDENTIFIER,identifier) || identifier==0)
      { g_uncertain=true; continue; }
      ulong id=(ulong)identifier,order=0,deal=0;
      int index=Track(id,ticket);
      if(index<0) { g_uncertain=true; continue; }
      if(g_positions[index].reconcile_exhausted ||
         g_positions[index].ownership==OWN_INCOMPATIBLE)
      { g_uncertain=true; continue; }
      // Repeated calls in the same callback cannot spend another inconclusive attempt.
      if(g_positions[index].ownership==OWN_INCONCLUSIVE &&
         g_positions[index].last_attempt_event==g_event_serial)
      { g_uncertain=true; continue; }
      g_positions[index].last_attempt_event=g_event_serial;
      string why;
      OwnershipState previous=g_positions[index].ownership;
      OwnershipState state=ProveOwnership(ticket,id,order,deal,why);
      g_positions[index].ownership=state;
      if(state!=previous || state!=OWN_CONFIRMED)
         if(OwnershipAllows(state!=OWN_CONFIRMED, true)) OwnershipLog(StringFormat("position=%I64u id=%I64u previous=%s state=%s inconclusive_attempts=%d reason=%s",
                      ticket,id,OwnershipName(previous),OwnershipName(state),
                      g_positions[index].inconclusive_attempts,why));
      if(state==OWN_INCOMPATIBLE)
      {
         g_uncertain=true;
         Halt("propriedade comprovadamente incompativel; nenhuma mutacao");
         continue;
      }
      if(state==OWN_INCONCLUSIVE)
      {
         g_uncertain=true;
         g_positions[index].inconclusive_attempts++;
         if(g_positions[index].inconclusive_attempts>=InpReconcileMaxAttempts)
         {
            g_positions[index].reconcile_exhausted=true;
            Halt("reconciliacao esgotada; historico continua INCONCLUSIVE");
         }
         continue;
      }
      g_positions[index].origin_order=order;
      g_positions[index].origin_deal=deal;
      if(state!=previous) Diagnostic("OWNERSHIP_CONFIRMED");
      LogPosition(index);
      if(!ProtectionAdequate(ticket)) RecoverPosition(index);
   }
   g_auditing=false;
}

void Enter(const int signal)
{
   if(!IsTester() || g_busy || g_halted || g_uncertain || HasExposure()) return;
   ENUM_ORDER_TYPE side=signal>0?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   string why;
   double volume,price,sl,tp;
   MqlTick q={};
   if(!FOKAllowed()) { LogBlock("FOK nao permitido; nenhum fallback IOC/RETURN"); return; }
   if(!Permissions(side,why) || !GetVolume(volume,why)) { LogBlock(why); return; }
   if(!SymbolInfoTick(InpSymbol,q) || q.time<=0) { LogBlock("sem cotacao"); return; }
   if(!BuildStops(side,q,price,sl,tp,why)) { LogBlock(why); return; }
   MqlTradeRequest request={};
   request.action=TRADE_ACTION_DEAL;
   request.magic=InpMagic;
   request.symbol=InpSymbol;
   request.volume=volume;
   request.price=price;
   request.sl=sl;
   request.tp=tp;
   request.deviation=InpDeviationPoints;
   request.type=side;
   request.type_filling=ORDER_FILLING_FOK;
   request.type_time=ORDER_TIME_GTC;
   request.comment="MT5SF001_ENTRY";
   if(!CheckRequest(request) || HasExposure() || g_halted || g_uncertain) return;
   g_requested_price=price;
   g_requested_side=side;
   g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   g_window_ticks=InpDiagnosticWindowTicks;
   Diagnostic("ENTRY_BEFORE_SEND");
   g_entry_requests++;
   g_busy=true;
   bool sent=g_trade.PositionOpen(InpSymbol,side,volume,price,sl,tp,request.comment);
   uint code=g_trade.ResultRetcode();
   g_last_order=g_trade.ResultOrder();
   RememberOrder(g_last_order);
   g_last_deal=g_trade.ResultDeal();
   double actual=g_trade.ResultPrice();
   double tick=SymbolInfoDouble(InpSymbol,SYMBOL_TRADE_TICK_SIZE);
   double adverse=(side==ORDER_TYPE_BUY?actual-price:price-actual);
   g_busy=false;
   ObserveEquity();
   Diagnostic("ENTRY_AFTER_SEND");
   PrintFormat("MT5SF001 ENTRY sent=%s code=%u description=%s order=%I64u deal=%I64u requested=%.8f executed=%.8f adverse_slippage=%.8f adverse_ticks=%.3f requested_volume=%.8f actual_volume=%.8f SL=%.8f TP=%.8f",
               sent?"true":"false",code,g_trade.ResultRetcodeDescription(),
               g_last_order,g_last_deal,price,actual,actual>0?adverse:0,
               actual>0 && tick>0?adverse/tick:0,volume,g_trade.ResultVolume(),sl,tp);
   if(!sent || code!=TRADE_RETCODE_DONE || g_last_deal==0 ||
      MathAbs(g_trade.ResultVolume()-volume)>1e-8)
      Halt("entrada rejeitada, parcial ou incerta; nao repetir");
   AuditExposure(); // inspect actual state even when the result was not definitive
}

ulong g_logged_deals[];

bool LogDeal(const ulong deal)
{
   if(deal==0) return true;
   for(int i=0;i<ArraySize(g_logged_deals);++i) if(g_logged_deals[i]==deal) return true;
   ResetLastError();
   bool selected=HistoryDealSelect(deal); int error=GetLastError();
   if(OwnershipAllows(!selected || error!=0)) OwnershipLog(StringFormat("query=HistoryDealSelect ticket=%I64u ok=%s error=%d",
                deal,selected?"true":"false",error));
   if(!selected) { g_uncertain=true; return false; }
   string symbol="";
   long magic=0,entry_kind=0,reason=0,deal_msc=0,order=0,id=0;
   double actual=0,volume=0,sl=0,tp=0,profit=0;
   bool readable=HDS(deal,DEAL_SYMBOL,symbol);
   if(!HDI(deal,DEAL_MAGIC,magic)) readable=false;
   if(!readable) { g_uncertain=true; return false; }
   if(symbol!=InpSymbol || (ulong)magic!=InpMagic) return true;
   readable=HDI(deal,DEAL_ENTRY,entry_kind);
   if(!HDI(deal,DEAL_REASON,reason)) readable=false;
   if(!HDI(deal,DEAL_TIME_MSC,deal_msc)) readable=false;
   if(!HDI(deal,DEAL_ORDER,order)) readable=false;
   if(!HDI(deal,DEAL_POSITION_ID,id)) readable=false;
   if(!HDD(deal,DEAL_PRICE,actual)) readable=false;
   if(!HDD(deal,DEAL_VOLUME,volume)) readable=false;
   if(!HDD(deal,DEAL_SL,sl)) readable=false;
   if(!HDD(deal,DEAL_TP,tp)) readable=false;
   if(!HDD(deal,DEAL_PROFIT,profit)) readable=false;
   if(!readable) { g_uncertain=true; return false; }
   int n=ArraySize(g_logged_deals);
   if(ArrayResize(g_logged_deals,n+1)!=n+1) { Halt("memoria de negocios indisponivel"); return true; }
   g_logged_deals[n]=deal;
   g_own_deals++;
   if(entry_kind==DEAL_ENTRY_OUT || entry_kind==DEAL_ENTRY_OUT_BY) g_exit_deals++;
   if(reason==DEAL_REASON_SL) g_sl_exits++;
   if(reason==DEAL_REASON_TP) g_tp_exits++;
   g_window_ticks=InpDiagnosticWindowTicks;
   ObserveEquity();
   Diagnostic(reason==DEAL_REASON_SL?"SL_DEAL":reason==DEAL_REASON_TP?"TP_DEAL":
              entry_kind==DEAL_ENTRY_IN?"ENTRY_DEAL":"EXIT_OR_OTHER_DEAL");
   bool known=((ulong)order==g_last_order && g_requested_price>0 && entry_kind==DEAL_ENTRY_IN);
   double adverse=known?(g_requested_side==ORDER_TYPE_BUY?
                         actual-g_requested_price:g_requested_price-actual):0;
   PrintFormat("MT5SF001 DEAL deal=%I64u order=%I64u position_id=%I64u magic=%I64u time_msc=%I64d entry_kind=%d volume=%.8f executed=%.8f requested_known=%s requested=%.8f adverse_slippage=%.8f SL=%.8f TP=%.8f reason=%d profit=%.2f",
               deal,(ulong)order,(ulong)id,(ulong)magic,deal_msc,(int)entry_kind,
               volume,actual,known?"true":"false",known?g_requested_price:0,
               adverse,sl,tp,(int)reason,profit);
   return true;
}

struct PendingDeal
{
   ulong ticket;
   int attempts;
   ulong last_event;
   bool resolved;
   bool exhausted;
};
PendingDeal g_pending_deals[];

void QueueDeal(const ulong ticket)
{
   if(ticket==0) return;
   for(int i=0;i<ArraySize(g_pending_deals);++i)
      if(g_pending_deals[i].ticket==ticket) return;
   int n=ArraySize(g_pending_deals);
   if(ArrayResize(g_pending_deals,n+1)!=n+1) { Halt("memoria de fila indisponivel"); return; }
   g_pending_deals[n].ticket=ticket; g_pending_deals[n].attempts=0;
   g_pending_deals[n].last_event=0; g_pending_deals[n].resolved=false;
   g_pending_deals[n].exhausted=false;
}

bool PendingDealsUnresolved()
{
   for(int i=0;i<ArraySize(g_pending_deals);++i)
      if(!g_pending_deals[i].resolved) return true;
   return false;
}

void ReconcileDeals()
{
   for(int i=0;i<ArraySize(g_pending_deals);++i)
   {
      if(g_pending_deals[i].resolved || g_pending_deals[i].exhausted ||
         g_pending_deals[i].last_event==g_event_serial) continue;
      g_pending_deals[i].last_event=g_event_serial;
      if(LogDeal(g_pending_deals[i].ticket)) g_pending_deals[i].resolved=true;
      else
      {
         g_pending_deals[i].attempts++;
         if(g_pending_deals[i].attempts>=InpReconcileMaxAttempts)
         {
            g_pending_deals[i].exhausted=true;
            Halt("leitura de negocio esgotada; historico permanece inconclusivo");
         }
      }
   }
}


// -------- Final read-only accounting, independent from callback counters --------
// These snapshots are recreated on each final call. No ownership proof, trading
// decision or callback counter uses a cached final result.
struct FinalOrder
{
   ulong ticket;
   long reported_ticket;
   long magic;
   long position_id;
   long state;
   string symbol;
   bool readable;
};
struct FinalDeal
{
   ulong ticket;
   long reported_ticket;
   long magic;
   long position_id;
   long order;
   long type;
   long entry;
   long reason;
   long time_msc;
   double volume;
   double price;
   double profit;
   double commission;
   double swap;
   double fee;
   string symbol;
   string comment;
   bool readable;
};
bool g_final_eligible=false;
bool g_final_seen=false;
string g_final_printed_signature="";
bool g_final_details_capped=false;

bool CallbackSawDeal(const ulong ticket)
{
   for(int i=0;i<ArraySize(g_pending_deals);++i)
      if(g_pending_deals[i].ticket==ticket) return true;
   return false;
}
bool CallbackProcessedDeal(const ulong ticket)
{
   for(int i=0;i<ArraySize(g_logged_deals);++i)
      if(g_logged_deals[i]==ticket) return true;
   return false;
}
bool FinalDetailAllowed()
{
   if(g_final_details<InpFinalMaxDetails) { g_final_details++; return true; }
   if(!g_final_details_capped)
   {
      Print("MT5SF001 FINAL: limite de detalhes atingido; apuracao completa continua.");
      g_final_details_capped=true;
   }
   return false;
}

// All tickets are enumerated into local arrays BEFORE any individual Select.
// The individual selections below can reset terminal lists without losing them.
bool ReadFinalSnapshots(FinalOrder &orders[],FinalDeal &deals[],string &why)
{
   ResetLastError();
   // Include the entire final second when deals carry millisecond timestamps.
   bool selected=HistorySelect(0,TimeCurrent()+1);
   int error=GetLastError();
   if(!selected)
   {
      why=StringFormat("HistorySelect failed error=%d",error);
      return false;
   }
   int no=HistoryOrdersTotal(),nd=HistoryDealsTotal();
   // A bounded allocation failure never turns a partial scan into a full result.
   if(no<0 || nd<0 || no>100000 || nd>100000)
   { why="final history size outside bounded scan capacity"; return false; }
   if(ArrayResize(orders,no)!=no || ArrayResize(deals,nd)!=nd)
   { why="final snapshot allocation failed"; return false; }
   bool enumeration_ok=true;
   for(int i=0;i<no;++i)
   {
      ResetLastError();
      orders[i].ticket=HistoryOrderGetTicket(i);
      int err=GetLastError();
      if(orders[i].ticket==0 || err!=0)
      {
         enumeration_ok=false;
         if(FinalDetailAllowed())
            PrintFormat("MT5SF001 FINAL order enumeration index=%d ticket=%I64u error=%d",
                        i,orders[i].ticket,err);
      }
   }
   for(int i=0;i<nd;++i)
   {
      ResetLastError();
      deals[i].ticket=HistoryDealGetTicket(i);
      int err=GetLastError();
      if(deals[i].ticket==0 || err!=0)
      {
         enumeration_ok=false;
         if(FinalDetailAllowed())
            PrintFormat("MT5SF001 FINAL deal enumeration index=%d ticket=%I64u error=%d",
                        i,deals[i].ticket,err);
      }
   }
   // Sort disposable ticket copies to detect duplicates without quadratic scans.
   ulong order_check[],deal_check[];
   if(ArrayResize(order_check,no)!=no || ArrayResize(deal_check,nd)!=nd)
   { why="duplicate-check allocation failed"; return false; }
   for(int i=0;i<no;++i) order_check[i]=orders[i].ticket;
   for(int i=0;i<nd;++i) deal_check[i]=deals[i].ticket;
   if(no>1)
   {
      if(!ArraySort(order_check)) { why="order ticket sort failed"; return false; }
      for(int i=1;i<no;++i) if(order_check[i]==order_check[i-1]) enumeration_ok=false;
   }
   if(nd>1)
   {
      if(!ArraySort(deal_check)) { why="deal ticket sort failed"; return false; }
      for(int i=1;i<nd;++i) if(deal_check[i]==deal_check[i-1]) enumeration_ok=false;
   }
   if(!enumeration_ok) { why="final ticket enumeration incomplete/duplicated"; return false; }

   for(int i=0;i<no;++i)
   {
      orders[i].reported_ticket=0; orders[i].magic=0; orders[i].position_id=0;
      orders[i].state=0; orders[i].symbol=""; orders[i].readable=false;
      ResetLastError();
      bool ok=HistoryOrderSelect(orders[i].ticket);
      int err=GetLastError();
      if(ok)
      {
         ok=HOI(orders[i].ticket,ORDER_TICKET,orders[i].reported_ticket);
         if(!HOI(orders[i].ticket,ORDER_MAGIC,orders[i].magic)) ok=false;
         if(!HOI(orders[i].ticket,ORDER_POSITION_ID,orders[i].position_id)) ok=false;
         if(!HOI(orders[i].ticket,ORDER_STATE,orders[i].state)) ok=false;
         if(!HOS(orders[i].ticket,ORDER_SYMBOL,orders[i].symbol)) ok=false;
      }
      orders[i].readable=ok && (ulong)orders[i].reported_ticket==orders[i].ticket;
      if(!orders[i].readable && FinalDetailAllowed())
         PrintFormat("MT5SF001 FINAL historical order inconclusive ticket=%I64u select_error=%d",
                     orders[i].ticket,err);
   }
   for(int i=0;i<nd;++i)
   {
      deals[i].reported_ticket=0; deals[i].magic=0; deals[i].position_id=0;
      deals[i].order=0; deals[i].type=-1; deals[i].entry=-1;
      deals[i].reason=-1; deals[i].time_msc=0;
      deals[i].volume=0; deals[i].price=0; deals[i].profit=0;
      deals[i].commission=0; deals[i].swap=0; deals[i].fee=0;
      deals[i].symbol=""; deals[i].comment=""; deals[i].readable=false;
      ResetLastError();
      bool ok=HistoryDealSelect(deals[i].ticket);
      int err=GetLastError();
      if(ok)
      {
         ok=HDI(deals[i].ticket,DEAL_TICKET,deals[i].reported_ticket);
         if(!HDI(deals[i].ticket,DEAL_MAGIC,deals[i].magic)) ok=false;
         if(!HDI(deals[i].ticket,DEAL_POSITION_ID,deals[i].position_id)) ok=false;
         if(!HDI(deals[i].ticket,DEAL_ORDER,deals[i].order)) ok=false;
         if(!HDI(deals[i].ticket,DEAL_TYPE,deals[i].type)) ok=false;
         if(!HDI(deals[i].ticket,DEAL_ENTRY,deals[i].entry)) ok=false;
         if(!HDI(deals[i].ticket,DEAL_REASON,deals[i].reason)) ok=false;
         if(!HDI(deals[i].ticket,DEAL_TIME_MSC,deals[i].time_msc)) ok=false;
         if(!HDS(deals[i].ticket,DEAL_SYMBOL,deals[i].symbol)) ok=false;
         if(!HDS(deals[i].ticket,DEAL_COMMENT,deals[i].comment)) ok=false;
         if(!HDD(deals[i].ticket,DEAL_VOLUME,deals[i].volume)) ok=false;
         if(!HDD(deals[i].ticket,DEAL_PRICE,deals[i].price)) ok=false;
         if(!HDD(deals[i].ticket,DEAL_PROFIT,deals[i].profit)) ok=false;
         if(!HDD(deals[i].ticket,DEAL_COMMISSION,deals[i].commission)) ok=false;
         if(!HDD(deals[i].ticket,DEAL_SWAP,deals[i].swap)) ok=false;
         if(!HDD(deals[i].ticket,DEAL_FEE,deals[i].fee)) ok=false;
      }
      deals[i].readable=ok && (ulong)deals[i].reported_ticket==deals[i].ticket;
      if(!deals[i].readable && FinalDetailAllowed())
         PrintFormat("MT5SF001 FINAL historical deal inconclusive ticket=%I64u select_error=%d",
                     deals[i].ticket,err);
   }
   why="tickets enumerated and properties snapshotted";
   return true;
}

bool FinalMarketDeal(const FinalDeal &deal)
{
   return deal.type==DEAL_TYPE_BUY || deal.type==DEAL_TYPE_SELL;
}

// Individual historical attribution, NOT permission to change a live position.
// Every accepted deal must link exactly to an equally owned historical order.
// A mixed position can contain separately identified own/foreign deals; no
// aggregate position ownership is inferred by this reporting-only routine.
bool FinalDealLinkOwned(const FinalDeal &deal,const FinalOrder &orders[],string &why)
{
   if(!deal.readable) { why="deal properties unreadable"; return false; }
   if(deal.symbol!=InpSymbol || (ulong)deal.magic!=InpMagic)
   { why="deal symbol/magic does not establish EA ownership"; return false; }
   if(deal.position_id==0 || deal.order==0 || deal.volume<=0 ||
      !MathIsValidNumber(deal.volume) || !MathIsValidNumber(deal.price) || deal.price<=0)
   { why="deal linkage/price/volume invalid"; return false; }
   int found=-1,matches=0;
   for(int i=0;i<ArraySize(orders);++i)
      if(orders[i].ticket==(ulong)deal.order) { found=i; matches++; }
   if(matches!=1 || found<0) { why="order lacks unique enumerated match"; return false; }
   if(!orders[found].readable || (ulong)orders[found].reported_ticket!=(ulong)deal.order ||
      orders[found].symbol!=deal.symbol || (ulong)orders[found].magic!=InpMagic ||
      orders[found].position_id!=deal.position_id ||
      (orders[found].state!=ORDER_STATE_FILLED && orders[found].state!=ORDER_STATE_CANCELED))
   { why="historical order properties do not establish ownership/linkage"; return false; }
   why="deal/order symbol, magic, ticket and position link verified";
   return true;
}

bool FinalOriginOwned(const long position_id,const FinalDeal &deals[],
                     const FinalOrder &orders[])
{
   if(position_id==0) return false;
   int earliest=-1;
   for(int i=0;i<ArraySize(deals);++i)
   {
      if(!FinalMarketDeal(deals[i]) || deals[i].position_id!=position_id) continue;
      if(!deals[i].readable) return false;
      if(earliest<0 || deals[i].time_msc<deals[earliest].time_msc ||
         (deals[i].time_msc==deals[earliest].time_msc && deals[i].ticket<deals[earliest].ticket))
         earliest=i;
   }
   if(earliest<0 || deals[earliest].entry!=DEAL_ENTRY_IN) return false;
   string why;
   return FinalDealLinkOwned(deals[earliest],orders,why);
}

void ReconcileFinal(const string phase)
{
   if(!IsTester()) return;
   if(!g_final_eligible)
   {
      PrintFormat("MT5SF001 FINAL phase=%s skipped=initialization_not_validated",phase);
      return;
   }
   // Only called from OnTester/OnDeinit. Never call AuditExposure, LogDeal,
   // OrderCheck, OrderSend, CTrade, repair, close or cancel from this routine.
   FinalOrder orders[];
   FinalDeal deals[];
   string why;
   if(!ReadFinalSnapshots(orders,deals,why))
   {
      PrintFormat("MT5SF001 FINAL phase=%s complete=false result=INCONCLUSIVE reason=%s callbacks_processed=%I64u",
                  phase,why,g_own_deals);
      return;
   }
   int count=ArraySize(deals);
   bool owned[],candidate[],seen[],processed[],possible_end[];
   string reasons[];
   if(ArrayResize(owned,count)!=count || ArrayResize(candidate,count)!=count ||
      ArrayResize(seen,count)!=count || ArrayResize(processed,count)!=count ||
      ArrayResize(possible_end,count)!=count || ArrayResize(reasons,count)!=count)
   {
      PrintFormat("MT5SF001 FINAL phase=%s complete=false result=INCONCLUSIVE allocation_failed",phase);
      return;
   }
   int confirmed=0,uncertain=0,other=0,nonmarket=0,unreadable=0;
   int entries=0,exits=0,sl=0,tp=0,history_without_callback=0,missing_processed=0;
   int callback_without_history=0,unprocessed_callbacks=0;
   double profit=0,costs=0;
   bool snapshot_complete=true;
   long end_msc=(long)TimeCurrent()*1000;
   string signature="";
   for(int i=0;i<ArraySize(orders);++i)
   {
      if(!orders[i].readable) snapshot_complete=false;
      signature+=StringFormat("O%I64u/%I64d/%I64d/%I64d/%I64d/%s/%s;",
                   orders[i].ticket,orders[i].reported_ticket,orders[i].magic,
                   orders[i].position_id,orders[i].state,orders[i].symbol,
                   orders[i].readable?"1":"0");
   }
   for(int i=0;i<count;++i)
   {
      owned[i]=false; candidate[i]=false;
      seen[i]=CallbackSawDeal(deals[i].ticket);
      processed[i]=CallbackProcessedDeal(deals[i].ticket);
      possible_end[i]=false; reasons[i]="";
      // Fingerprint for print deduplication only; full reads/validation occur
      // on BOTH calls and no totals are incrementally accumulated.
      signature+=StringFormat("%I64u/%s/%I64d/%I64d/%I64d/%I64d/%I64d/%I64d/%I64d/%.8f/%.8f/%.8f/%s;",
                  deals[i].ticket,deals[i].symbol,deals[i].magic,deals[i].position_id,
                  deals[i].order,deals[i].entry,deals[i].reason,deals[i].time_msc,
                  deals[i].type,deals[i].volume,deals[i].price,deals[i].profit,
                  deals[i].readable?"1":"0");
      if(!deals[i].readable)
      {
         unreadable++; uncertain++; snapshot_complete=false; candidate[i]=true;
         reasons[i]="unreadable record; no ownership attribution";
         continue;
      }
      if(!FinalMarketDeal(deals[i])) { nonmarket++; continue; }
      if(deals[i].symbol!=InpSymbol) { other++; continue; }
      bool own_origin=FinalOriginOwned(deals[i].position_id,deals,orders);
      candidate[i]=(deals[i].symbol==InpSymbol &&
                    ((ulong)deals[i].magic==InpMagic || own_origin || seen[i] || processed[i]));
      if(!candidate[i]) { other++; continue; }
      bool linked=FinalDealLinkOwned(deals[i],orders,reasons[i]);
      owned[i]=linked && own_origin;
      if(linked && !own_origin) reasons[i]="initial position origin not proven";
      bool exit=(deals[i].entry==DEAL_ENTRY_OUT || deals[i].entry==DEAL_ENTRY_OUT_BY);
      // Heuristic only. There is no dedicated DEAL_REASON_END_OF_TEST.
      // Missing callback + final-time exit never overrides failed ownership.
      possible_end[i]=exit && !seen[i] && deals[i].time_msc>=end_msc-1000 &&
                      deals[i].time_msc<=end_msc+999 &&
                      deals[i].reason!=DEAL_REASON_SL && deals[i].reason!=DEAL_REASON_TP;
      if(!owned[i]) { uncertain++; continue; }
      confirmed++;
      if(deals[i].entry==DEAL_ENTRY_IN) entries++;
      if(exit) exits++;
      if(deals[i].reason==DEAL_REASON_SL) sl++;
      if(deals[i].reason==DEAL_REASON_TP) tp++;
      profit+=deals[i].profit;
      costs+=deals[i].commission+deals[i].swap+deals[i].fee;
      if(!seen[i]) history_without_callback++;
      if(!processed[i]) missing_processed++;
   }
   for(int i=0;i<ArraySize(g_logged_deals);++i)
   {
      bool found=false;
      for(int j=0;j<count;++j) if(deals[j].ticket==g_logged_deals[i]) { found=true; break; }
      if(!found) callback_without_history++;
   }
   for(int i=0;i<ArraySize(g_pending_deals);++i)
      if(!CallbackProcessedDeal(g_pending_deals[i].ticket)) unprocessed_callbacks++;

   // Tester-wide statistics are not automatically attributable to this EA.
   double stat_deals=TesterStatistics(STAT_DEALS);
   double stat_trades=TesterStatistics(STAT_TRADES);
   double stat_profit=TesterStatistics(STAT_PROFIT);
   signature+=StringFormat("|orders=%d|confirmed=%d|uncertain=%d|callbacks=%I64u|seen=%d|stats=%.8f/%.8f/%.8f|costs=%.8f",
                ArraySize(orders),confirmed,uncertain,g_own_deals,
                ArraySize(g_pending_deals),stat_deals,stat_trades,stat_profit,costs);
   bool unchanged=g_final_seen && signature==g_final_printed_signature;
   // A fresh final result is computed above even when the print is unchanged.
   PrintFormat("MT5SF001 FINAL phase=%s snapshot_unchanged=%s scan_complete=%s history_confirmed_own_deals=%d history_own_entries=%d history_own_exits=%d history_SL=%d history_TP=%d inconclusive_records=%d unreadable=%d other_market_deals=%d nonmarket_records=%d callback_observed_all=%d callback_processed_own=%I64u history_own_without_callback=%d history_own_without_processed_callback=%d processed_callback_without_history=%d queued_unprocessed=%d history_own_gross_profit=%.2f history_own_costs=%.2f history_own_net=%.2f tester_ALL_deals=%.0f tester_ALL_trades=%.0f tester_ALL_profit=%.2f",
               phase,unchanged?"true":"false",snapshot_complete?"true":"false",
               confirmed,entries,exits,sl,tp,uncertain,unreadable,other,nonmarket,
               ArraySize(g_pending_deals),g_own_deals,history_without_callback,missing_processed,
               callback_without_history,unprocessed_callbacks,profit,costs,profit+costs,
               stat_deals,stat_trades,stat_profit);
   PrintFormat("MT5SF001 FINAL_DIFFERENCES phase=%s history_confirmed_minus_callback_processed=%I64d tester_ALL_minus_history_confirmed_deals=%.0f tester_ALL_minus_history_confirmed_net=%.2f attribution_of_tester_totals=NOT_ASSUMED",
               phase,(long)confirmed-(long)g_own_deals,stat_deals-(double)confirmed,
               stat_profit-(profit+costs));
   Print("MT5SF001 FINAL: TesterStatistics abrange TODO o teste; fechamento de fim",
         " de teste e apenas candidato quando indicado. Nenhuma negociacao na reconciliacao.");
   if(!unchanged)
   {
      for(int i=0;i<count;++i)
      {
         if(!candidate[i]) continue;
         if(!FinalDetailAllowed()) break;
         PrintFormat("MT5SF001 FINAL_DEAL phase=%s ticket=%I64u result=%s symbol=%s magic=%I64d position_id=%I64d order=%I64d entry=%I64d reason=%I64d time_msc=%I64d price=%.8f volume=%.8f profit=%.2f callback_seen=%s callback_processed=%s possible_end_of_test=%s evidence=%s",
                     phase,deals[i].ticket,owned[i]?"CONFIRMED":"INCONCLUSIVE",
                     deals[i].symbol,deals[i].magic,deals[i].position_id,deals[i].order,
                     deals[i].entry,deals[i].reason,deals[i].time_msc,deals[i].price,
                     deals[i].volume,deals[i].profit,seen[i]?"true":"false",
                     processed[i]?"true":"false",possible_end[i]?"true":"false",reasons[i]);
      }
   }
   g_final_seen=true;
   g_final_printed_signature=signature;
}

double OnTester()
{
   if(!IsTester()) return 0.0;
   ReconcileFinal("OnTester");
   return 0.0; // Reporting only; no optimization or trading is initiated.
}

int OnInit()
{
   if(!IsTester())
   {
      Print("MT5SF001: inicializacao recusada fora do Strategy Tester.");
      return INIT_FAILED;
   }
   if(InpOwnershipFailureMaxRecords<1 || InpOwnershipFailureMaxRecords>20000 ||
      InpFinalMaxDetails<1 || InpFinalMaxDetails>10000 ||
      InpDiagnosticMaxRecords<1 || InpDiagnosticMaxRecords>10000 ||
      InpOwnershipMaxRecords<1 || InpOwnershipMaxRecords>20000 ||
      InpReconcileMaxAttempts<1 || InpReconcileMaxAttempts>100 ||
      InpDiagnosticWindowTicks<0 || InpDiagnosticWindowTicks>1000 ||
      !MathIsValidNumber(InpEquityExtremeStep) || InpEquityExtremeStep<=0 ||
      InpSymbol=="" || InpSymbol!=_Symbol || InpTimeframe==PERIOD_CURRENT ||
      InpTimeframe!=(ENUM_TIMEFRAMES)_Period ||
      InpFastPeriod<1 || InpSlowPeriod<=InpFastPeriod || InpSlowPeriod>100000 ||
      InpMagic==0 || !MathIsValidNumber(InpShares) || InpShares<=0 ||
      !MathIsValidNumber(InpStopLossPercent) || InpStopLossPercent<=0 ||
      InpStopLossPercent>=100 || !MathIsValidNumber(InpTakeProfitPercent) ||
      InpTakeProfitPercent<=0 || InpTakeProfitPercent>=100)
      return INIT_PARAMETERS_INCORRECT;
   if(!SymbolInfoInteger(InpSymbol,SYMBOL_SELECT)) return INIT_FAILED;
   g_final_eligible=true; // valid Tester inputs/symbol; reporting never submits trades
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   g_trade.SetAsyncMode(false);
   g_trade.SetMarginMode();
   g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   // Reconstruct ownership from actual positions/orders/history before entries.
   // Do NOT trust or assume any prior g_halted value after reinitialization.
   g_event_serial++;
   ObserveEquity();
   Diagnostic("INIT_BEFORE_AUDIT");
   AuditExposure();
   Diagnostic("INIT_AFTER_AUDIT");
   double volume; string why;
   if(!GetVolume(volume,why))
   {
      LogBlock(why);
      Halt("volume configurado invalido; auditoria continua ativa");
   }
   if(!FOKAllowed())
   {
      LogBlock("FOK indisponivel; entradas bloqueadas");
      Halt("simbolo sem FOK");
   }
   g_fast=iMA(InpSymbol,InpTimeframe,InpFastPeriod,0,MODE_EMA,InpAppliedPrice);
   g_slow=iMA(InpSymbol,InpTimeframe,InpSlowPeriod,0,MODE_EMA,InpAppliedPrice);
   if(g_fast==INVALID_HANDLE || g_slow==INVALID_HANDLE)
   {
      // Keep EA attached to audit exposure, but never trade on invalid handles.
      Halt("indicadores indisponiveis");
   }
   g_bar=iTime(InpSymbol,InpTimeframe,0);
   Print("MT5SF001 v1.22: Tester only. FOK only. Auditoria na inicializacao,",
         " transacoes, OnTrade e ticks. Uma tentativa de reparo/fechamento por",
         " identificador e cancelamento por ticket, registrados no ambiente Tester.");
   Print("MT5SF001: apos reinicializacao, exposicao e propriedade sao reavaliadas;",
         " limites persistidos no Tester sao respeitados. SL nao garante perda maxima de 1%.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(IsTester()) ReconcileFinal("OnDeinit");
   if(g_fast!=INVALID_HANDLE) IndicatorRelease(g_fast);
   if(g_slow!=INVALID_HANDLE) IndicatorRelease(g_slow);
   ObserveEquity();
   Diagnostic("DEINIT");
   PrintFormat("MT5SF001 SUMMARY evaluated_signals=%I64u entry_requests=%I64u logged_own_deals=%I64u exit_deals=%I64u SL_exits=%I64u TP_exits=%I64u observed_equity_high=%.8f observed_equity_low=%.8f diag_records=%d ownership_records=%d uncertain=%s",
               g_signal_count,g_entry_requests,g_own_deals,g_exit_deals,g_sl_exits,g_tp_exits,
               g_equity_high,g_equity_low,g_diagnostic_count,g_ownership_count,g_uncertain?"true":"false");
   PrintFormat("MT5SF001 LOG_SUMMARY ownership_success_printed=%d ownership_failure_printed=%d success_suppressed=%I64u failure_suppressed=%I64u final_detail_printed=%d",
               g_ownership_count,g_ownership_failure_count,g_ownership_success_suppressed,
               g_ownership_failure_suppressed,g_final_details);
   PrintFormat("MT5SF001: deinit reason=%d halted=%s; nenhuma ordem enviada no deinit",
               reason,g_halted?"true":"false");
}


void OnTick()
{
   if(!IsTester()) return;
   g_event_serial++;
   ObserveEquity();
   if(g_window_ticks>0) { Diagnostic("TICK_WINDOW"); g_window_ticks--; }
   ReconcileDeals();
   AuditExposure(); // audits and recovery remain active while entries are blocked
   ObserveEquity();
   if(g_halted || g_uncertain || g_busy) return;
   datetime bar=iTime(InpSymbol,InpTimeframe,0);
   if(bar<=0) return;
   if(g_bar==0) { g_bar=bar; return; }
   if(bar<=g_bar) return;
   g_bar=bar;
   if(HasExposure()) return;
   int signal;
   if(!ReadSignal(signal)) { LogBlock("dados EMA indisponiveis; candle descartado"); return; }
   if(signal!=0)
   {
      g_signal_count++;
      Diagnostic(signal>0?"BUY_SIGNAL_CLOSED_BAR":"SELL_SIGNAL_CLOSED_BAR");
      Enter(signal);
   }
}


void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(!IsTester()) return;
   bool own_request=(trans.type==TRADE_TRANSACTION_REQUEST &&
                     request.symbol==InpSymbol && request.magic==InpMagic);
   if(trans.symbol!=InpSymbol && !own_request) return;
   g_event_serial++;
   ObserveEquity();
   g_window_ticks=InpDiagnosticWindowTicks;
   Diagnostic("TRADE_TRANSACTION");
   if(OwnershipAllows(false, true)) OwnershipLog(StringFormat("transaction.type=%s order=%I64u deal=%I64u position_ticket=%I64u position_by=%I64u price=%.8f volume=%.8f",
                EnumToString(trans.type),trans.order,trans.deal,trans.position,
                trans.position_by,trans.price,trans.volume));
   if(own_request)
   {
      RememberOrder(result.order);
      PrintFormat("MT5SF001 TRANSACTION action=%d magic=%I64u position=%I64u order=%I64u deal=%I64u request_id=%u retcode=%u comment=%s",
                  (int)request.action,request.magic,request.position,result.order,result.deal,
                  result.request_id,result.retcode,result.comment);
      if(result.retcode!=TRADE_RETCODE_DONE)
         Halt("retorno transacional nao final ou rejeitado");
   }
   if(trans.type==TRADE_TRANSACTION_DEAL_ADD) QueueDeal(trans.deal);
   ReconcileDeals();
   AuditExposure();
   ObserveEquity();
}

void OnTrade()
{
   if(!IsTester()) return;
   g_event_serial++;
   ObserveEquity();
   Diagnostic("ON_TRADE");
   ReconcileDeals();
   AuditExposure();
   ObserveEquity();
}
