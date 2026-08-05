import { GaugeChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactEChartsCore from "echarts-for-react/lib/core";
import type { CSSProperties } from "react";

echarts.use([
  GaugeChart,
  GridComponent,
  LegendComponent,
  LineChart,
  MarkLineComponent,
  PieChart,
  TooltipComponent,
  CanvasRenderer,
]);

interface ChartProps {
  option: EChartsCoreOption;
  style?: CSSProperties;
}

export function Chart({ option, style }: ChartProps) {
  return <ReactEChartsCore echarts={echarts} option={option} style={style} />;
}
