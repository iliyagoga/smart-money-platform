package com.smartmoney.data.repository;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartmoney.data.model.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import java.math.BigDecimal;
import java.util.List;

@Repository
public class MarketRepository {
    private final JdbcClient db;
    private final ObjectMapper json;
    public MarketRepository(JdbcClient db, ObjectMapper json) { this.db = db; this.json = json; }

    public void save(Candle c) {
        db.sql("""
          INSERT INTO candles(symbol,timeframe,ts,open,high,low,close,volume,quote_volume,trades_count,is_closed)
          VALUES (:symbol,:tf,to_timestamp(:ts/1000.0),:open,:high,:low,:close,:volume,:qv,:count,:closed)
          ON CONFLICT(symbol,timeframe,ts) DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,
          close=excluded.close,volume=excluded.volume,quote_volume=excluded.quote_volume,
          trades_count=excluded.trades_count,is_closed=excluded.is_closed
          """).param("symbol", c.symbol()).param("tf", c.timeframe().name()).param("ts", c.timestamp())
          .param("open", c.open()).param("high", c.high()).param("low", c.low()).param("close", c.close())
          .param("volume", c.volume()).param("qv", c.quoteVolume()).param("count", c.tradesCount())
          .param("closed", c.isClosed()).update();
    }

    public void save(MarketTick t) {
        db.sql("""
          INSERT INTO market_ticks(symbol,trade_id,ts,price,volume,side)
          VALUES(:symbol,:id,to_timestamp(:ts/1000.0),:price,:volume,:side) ON CONFLICT(symbol,trade_id,ts) DO NOTHING
          """)
          .param("symbol",t.symbol()).param("id",t.tradeId()).param("ts",t.timestamp()).param("price",t.price())
          .param("volume",t.volume()).param("side",t.side().name()).update();
    }

    public void save(OrderBook b) {
        try {
            db.sql("""
              INSERT INTO order_books(symbol,ts,sequence_id,bids,asks)
              VALUES(:symbol,to_timestamp(:ts/1000.0),:seq,CAST(:bids AS jsonb),CAST(:asks AS jsonb))
              ON CONFLICT(symbol,ts) DO UPDATE SET sequence_id=excluded.sequence_id,bids=excluded.bids,asks=excluded.asks
              """)
              .param("symbol",b.symbol()).param("ts",b.timestamp()).param("seq",b.sequenceId())
              .param("bids",json.writeValueAsString(b.bids())).param("asks",json.writeValueAsString(b.asks())).update();
        } catch (JsonProcessingException e) { throw new IllegalArgumentException("Invalid order book", e); }
    }

    public List<Candle> candles(String symbol, Timeframe tf, Long from, Long to, int limit) {
        return db.sql("""
          SELECT symbol,timeframe,(extract(epoch from ts)*1000)::bigint ts,open,high,low,close,
          volume,quote_volume,trades_count,is_closed FROM candles WHERE symbol=:symbol AND timeframe=:tf
          AND (CAST(:fromTs AS bigint) IS NULL OR ts>=to_timestamp(CAST(:fromTs AS double precision)/1000.0))
          AND (CAST(:toTs AS bigint) IS NULL OR ts<=to_timestamp(CAST(:toTs AS double precision)/1000.0))
          ORDER BY ts DESC LIMIT :limit
          """).param("symbol",symbol).param("tf",tf.name()).param("fromTs",from)
          .param("toTs",to).param("limit",limit).query((rs,n)->new Candle(rs.getString("symbol"), Timeframe.valueOf(rs.getString("timeframe")),
              rs.getLong("ts"),rs.getBigDecimal("open"),rs.getBigDecimal("high"),rs.getBigDecimal("low"),rs.getBigDecimal("close"),
              rs.getBigDecimal("volume"),rs.getBigDecimal("quote_volume"),(Long)rs.getObject("trades_count"),rs.getBoolean("is_closed"))).list();
    }

    public List<MarketTick> ticks(String symbol, Long from, Long to, int limit) {
        return db.sql("""
          SELECT symbol,trade_id,(extract(epoch from ts)*1000)::bigint ts,price,volume,side
          FROM market_ticks WHERE symbol=:symbol
          AND (CAST(:fromTs AS bigint) IS NULL OR ts>=to_timestamp(CAST(:fromTs AS double precision)/1000.0))
          AND (CAST(:toTs AS bigint) IS NULL OR ts<=to_timestamp(CAST(:toTs AS double precision)/1000.0))
          ORDER BY ts DESC LIMIT :limit
          """)
          .param("symbol",symbol).param("fromTs",from).param("toTs",to).param("limit",limit)
          .query((rs,n)->new MarketTick(rs.getString("symbol"),rs.getString("trade_id"),rs.getLong("ts"),
              rs.getBigDecimal("price"),rs.getBigDecimal("volume"),Side.valueOf(rs.getString("side")))).list();
    }

    public OrderBook latestOrderBook(String symbol) {
        return db.sql("""
          SELECT symbol,(extract(epoch from ts)*1000)::bigint ts,sequence_id,bids::text,asks::text
          FROM order_books WHERE symbol=:symbol ORDER BY ts DESC LIMIT 1
          """).param("symbol",symbol)
          .query((rs,n)->new OrderBook(rs.getString("symbol"),rs.getLong("ts"),rs.getLong("sequence_id"),
              levels(rs.getString("bids")),levels(rs.getString("asks")))).optional().orElse(null);
    }
    private List<OrderBook.Level> levels(String value) {
        try { return json.readerForListOf(OrderBook.Level.class).readValue(value); }
        catch (JsonProcessingException e) { throw new IllegalStateException("Stored order book is invalid",e); }
    }
}
