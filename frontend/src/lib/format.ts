const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const compactCurrencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const signedPercentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "always",
});

const axisPercentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

const countFormatter = new Intl.NumberFormat("en-US");

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function formatCurrency(value: number) {
  return currencyFormatter.format(value);
}

export function formatSignedCurrency(value: number) {
  const formatted = currencyFormatter.format(Math.abs(value));
  return value >= 0 ? `+${formatted}` : `-${formatted}`;
}

export function formatAxisCurrency(value: number) {
  return compactCurrencyFormatter.format(value);
}

export function formatPct(value: number) {
  return percentFormatter.format(value / 100);
}

export function formatSignedPct(value: number) {
  return signedPercentFormatter.format(value / 100);
}

export function formatAxisPct(value: number) {
  return axisPercentFormatter.format(value / 100);
}

export function formatCount(value: number) {
  return countFormatter.format(value);
}

export function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return dateTimeFormatter.format(parsed);
}
