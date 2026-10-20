package com.smartmoney.data.service;

import com.smartmoney.data.model.*;
import com.smartmoney.data.repository.MarketRepository;
import org.junit.jupiter.api.*;
import java.math.BigDecimal;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MarketDataServiceTest {
    private final MarketRepository repository=mock(MarketRepository.class);
    private final EventPublisher publisher=mock(EventPublisher.class);
    private final MarketDataService service=new MarketDataService(repository,publisher);

    @Test void storesAndPublishesValidCandle() {
        Candle c=new Candle("BTC-USDT-SWAP",Timeframe.M1,1000,bd("10"),bd("12"),bd("9"),bd("11"),bd("3"),null,null,true);
        service.ingest(c,"correlation");
        verify(repository).save(c); verify(publisher).publish("candle.update",c,"correlation");
    }
    @Test void rejectsInconsistentCandle() {
        Candle c=new Candle("BTC-USDT-SWAP",Timeframe.M1,1000,bd("13"),bd("12"),bd("9"),bd("11"),bd("3"),null,null,true);
        assertThrows(IllegalArgumentException.class,()->service.ingest(c,null));
        verifyNoInteractions(repository,publisher);
    }
    @Test void storesHistoricalBatchWithoutPublishingLiveEvents() {
        Candle first=new Candle("BTC-USDT-SWAP",Timeframe.M1,1000,bd("10"),bd("12"),bd("9"),bd("11"),bd("3"),null,null,true);
        Candle second=new Candle("BTC-USDT-SWAP",Timeframe.M1,61000,bd("11"),bd("13"),bd("10"),bd("12"),bd("4"),null,null,true);
        service.ingestBatch(List.of(first,second));
        verify(repository).save(first);verify(repository).save(second);verifyNoInteractions(publisher);
    }
    @Test void rejectsReversedTimeRange() {
        assertThrows(IllegalArgumentException.class,()->service.ticks("BTC-USDT-SWAP",20L,10L,50));
    }
    private static BigDecimal bd(String value) { return new BigDecimal(value); }
}
