package com.smartmoney.data.api;

import com.smartmoney.data.model.*;
import com.smartmoney.data.service.MarketDataService;
import jakarta.validation.constraints.*;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@Validated
@RestController
@RequestMapping("/market")
public class MarketController {
    private final MarketDataService service;
    public MarketController(MarketDataService service) { this.service=service; }

    @GetMapping("/candles")
    public Map<String,Object> candles(@RequestParam @NotBlank String symbol, @RequestParam Timeframe timeframe,
        @RequestParam(required=false) @PositiveOrZero Long from, @RequestParam(required=false) @PositiveOrZero Long to,
        @RequestParam(defaultValue="500") @Min(1) @Max(10000) int limit) {
        return Map.of("symbol",symbol.trim().toUpperCase(),"timeframe",timeframe,"candles",service.candles(symbol,timeframe,from,to,limit));
    }
    @GetMapping("/ticks")
    public Map<String,Object> ticks(@RequestParam @NotBlank String symbol,
        @RequestParam(required=false) @PositiveOrZero Long from, @RequestParam(required=false) @PositiveOrZero Long to,
        @RequestParam(defaultValue="500") @Min(1) @Max(1000) int limit) {
        return Map.of("symbol",symbol.trim().toUpperCase(),"ticks",service.ticks(symbol,from,to,limit));
    }
    @GetMapping("/orderbook")
    public OrderBook orderbook(@RequestParam @NotBlank String symbol,
        @RequestParam(defaultValue="10") @Min(1) @Max(100) int depth) { return service.orderBook(symbol,depth); }
}
