package com.smartmoney.data.model;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record Candle(
    @NotBlank String symbol, @NotNull Timeframe timeframe, @PositiveOrZero long timestamp,
    @NotNull @Positive BigDecimal open, @NotNull @Positive BigDecimal high,
    @NotNull @Positive BigDecimal low, @NotNull @Positive BigDecimal close,
    @NotNull @PositiveOrZero BigDecimal volume, @PositiveOrZero BigDecimal quoteVolume,
    @PositiveOrZero Long tradesCount, boolean isClosed
) {}
