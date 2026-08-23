package com.smartmoney.data.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.List;

public record OrderBook(
    @NotBlank String symbol, @PositiveOrZero long timestamp, @PositiveOrZero long sequenceId,
    @NotNull List<@Valid Level> bids, @NotNull List<@Valid Level> asks
) {
    @JsonFormat(shape = JsonFormat.Shape.ARRAY)
    public record Level(@NotNull @Positive BigDecimal price, @NotNull @PositiveOrZero BigDecimal volume) {}
}
