// Offline research source. Native status: native_validation_pending.
#property indicator_separate_window
#property indicator_buffers 1
#property indicator_plots 1
#property indicator_type1 DRAW_LINE
#property indicator_label1 "Wilder ATR"
#property indicator_color1 clrDodgerBlue

input int Period = 14;
double AtrBuffer[];

int OnInit()
{
   if(Period < 1)
      return INIT_PARAMETERS_INCORRECT;
   if(!SetIndexBuffer(0, AtrBuffer, INDICATOR_DATA))
      return INIT_FAILED;
   ArraySetAsSeries(AtrBuffer, false);
   PlotIndexSetInteger(0, PLOT_DRAW_BEGIN, Period - 1);
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   return INIT_SUCCEEDED;
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   ArraySetAsSeries(high, false);
   ArraySetAsSeries(low, false);
   ArraySetAsSeries(close, false);

   ArrayInitialize(AtrBuffer, EMPTY_VALUE);
   double average = 0.0;
   for(int i = 0; i < rates_total; i++)
   {
      if(!MathIsValidNumber(high[i]) || !MathIsValidNumber(low[i]) ||
         !MathIsValidNumber(close[i]) || high[i] == EMPTY_VALUE ||
         low[i] == EMPTY_VALUE || close[i] == EMPTY_VALUE || high[i] < low[i])
         break;

      double true_range = high[i] - low[i];
      if(i > 0)
         true_range = MathMax(true_range, MathMax(MathAbs(high[i] - close[i - 1]),
                                                 MathAbs(low[i] - close[i - 1])));
      if(!MathIsValidNumber(true_range))
         break;

      int divisor = i < Period ? i + 1 : Period;
      average += (true_range - average) / divisor;
      AtrBuffer[i] = i >= Period - 1 ? average : EMPTY_VALUE;
   }
   return rates_total;
}
