
export interface LayoutMetrics {
  rowH: number;
  uNumW: number;
  unit: number;
  titleFontSize: number;
  infoFontSize: number;
  uNumFontSize: number;
  showSidePanel: boolean;
  contentWidth: number;
}

export function computeLayout(containerWidth: number): LayoutMetrics {
  const isXs = containerWidth < 280;
  const isSm = containerWidth >= 280 && containerWidth < 400;
  const isMd = containerWidth >= 400 && containerWidth < 600;

  const rowH = isXs ? 20 : isSm ? 22 : isMd ? 26 : 28;
  const unit = rowH + 2; // ROW_GAP

  const uNumW = isXs ? 22 : isSm ? 28 : 32;

  const titleFontSize = isXs ? 8 : isSm ? 9 : isMd ? 11 : 12;
  const infoFontSize = isXs ? 7 : isSm ? 8 : isMd ? 9 : 9;
  const uNumFontSize = isXs ? 8 : isSm ? 9 : 10;

  const contentWidth = containerWidth - uNumW - 12; // 减去U编号列和边距

  const showSidePanel = containerWidth > 500;

  return {
    rowH,
    uNumW,
    unit,
    titleFontSize,
    infoFontSize,
    uNumFontSize,
    showSidePanel,
    contentWidth
  };
}

export function computeBlockInfoVisibility(
  blockHeight: number,
  contentWidth: number,
  rowH: number
) {
  const showInfoLine = contentWidth > 100 && blockHeight >= rowH * 1.8;
  const showModelLine = contentWidth > 150 && blockHeight >= rowH * 2.8;
  const showSnLine = contentWidth > 200 && blockHeight >= rowH * 3.8;
  const showInlineInfo = !showInfoLine && contentWidth > 180;
  return { showInfoLine, showModelLine, showSnLine, showInlineInfo };
}
