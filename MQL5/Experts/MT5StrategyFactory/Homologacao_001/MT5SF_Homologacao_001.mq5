#property strict
#property version "1.00"
#property description "MT5 Strategy Factory - homologacao sem negociacao"

int OnInit()
{
   if(!MQLInfoInteger(MQL_TESTER))
   {
      Print("Inicializacao recusada: uso exclusivo no Strategy Tester.");
      return INIT_FAILED;
   }

   Print("MT5 Strategy Factory: homologacao inicializada.");
   return INIT_SUCCEEDED;
}

void OnTick()
{
}
