package com.smartmoney.data.model;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record MarketTick(
    @NotBlank String symbol, @NotBlank String tradeId, @PositiveOrZero long timestamp,
    @NotNull @Positive BigDecimal price, @NotNull @Positive BigDecimal volume, @NotNull Side side
) {}
