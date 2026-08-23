package com.smartmoney.data.api;

import com.smartmoney.data.model.*;
import com.smartmoney.data.service.MarketDataService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/internal/ingest")
public class IngestionController {
    private final MarketDataService service;
    public IngestionController(MarketDataService service) { this.service=service; }
    @PostMapping("/candles") @ResponseStatus(HttpStatus.ACCEPTED)
    public Map<String,Boolean> candle(@Valid @RequestBody Candle value, @RequestHeader(value="X-Correlation-ID",required=false) String id) {
        service.ingest(value,id); return Map.of("accepted",true);
    }
    @PostMapping("/ticks") @ResponseStatus(HttpStatus.ACCEPTED)
    public Map<String,Boolean> tick(@Valid @RequestBody MarketTick value, @RequestHeader(value="X-Correlation-ID",required=false) String id) {
        service.ingest(value,id); return Map.of("accepted",true);
    }
    @PostMapping("/orderbook") @ResponseStatus(HttpStatus.ACCEPTED)
    public Map<String,Boolean> orderbook(@Valid @RequestBody OrderBook value, @RequestHeader(value="X-Correlation-ID",required=false) String id) {
        service.ingest(value,id); return Map.of("accepted",true);
    }
}
