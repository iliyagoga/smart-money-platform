package com.smartmoney.data.service;

import com.smartmoney.data.model.*;
import com.smartmoney.data.repository.MarketRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class MarketDataService {
    private final MarketRepository repository;
    private final EventPublisher events;
    public MarketDataService(MarketRepository repository, EventPublisher events) { this.repository=repository; this.events=events; }

    @Transactional public void ingest(Candle value, String correlationId) {
        validate(value);
        repository.save(value); events.publish("candle.update", value, correlationId);
    }
    @Transactional public void ingestBatch(List<Candle> values) {
        values.forEach(this::validate);
        repository.saveBatch(values);
    }
    @Transactional public void ingest(MarketTick value, String correlationId) {
        repository.save(value); events.publish("trade.executed", value, correlationId);
    }
    @Transactional public void ingest(OrderBook value, String correlationId) {
        repository.save(value); events.publish("orderbook.updated", value, correlationId);
    }
    @Transactional(readOnly=true) public List<Candle> candles(String symbol, Timeframe tf, Long from, Long to, int limit) {
        validateRange(from,to); return repository.candles(normalize(symbol),tf,from,to,limit);
    }
    @Transactional(readOnly=true) public List<MarketTick> ticks(String symbol, Long from, Long to, int limit) {
        validateRange(from,to); return repository.ticks(normalize(symbol),from,to,limit);
    }
    @Transactional(readOnly=true) public OrderBook orderBook(String symbol, int depth) {
        OrderBook b=repository.latestOrderBook(normalize(symbol));
        if (b==null) throw new NotFoundException("Order book not found");
        return new OrderBook(b.symbol(),b.timestamp(),b.sequenceId(),b.bids().stream().limit(depth).toList(),b.asks().stream().limit(depth).toList());
    }
    private void validateRange(Long from, Long to) { if(from!=null && to!=null && from>to) throw new IllegalArgumentException("from must not exceed to"); }
    private void validate(Candle value) {
        if (value.low().compareTo(value.high()) > 0 || value.open().compareTo(value.low()) < 0 || value.open().compareTo(value.high()) > 0
            || value.close().compareTo(value.low()) < 0 || value.close().compareTo(value.high()) > 0)
            throw new IllegalArgumentException("OHLC values are inconsistent");
    }
    private String normalize(String symbol) { return symbol.trim().toUpperCase(); }
}
