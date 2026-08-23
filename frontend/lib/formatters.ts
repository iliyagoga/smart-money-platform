const moneyFormatter = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 2,
});

export const formatMoney = (value?: number): string => moneyFormatter.format(value ?? 0);

export const formatSignedMoney = (value?: number): string => {
  const safeValue = value ?? 0;
  return `${safeValue >= 0 ? "+" : ""}${formatMoney(safeValue)}`;
};
