package com.smartmoney.data.model;

import java.time.Instant;
import java.util.UUID;

public record EventEnvelope(String messageId, String correlationId, long timestamp, String source,
                            String version, String eventType, Object payload) {
    public static EventEnvelope of(String type, Object payload, String correlationId) {
        return new EventEnvelope(UUID.randomUUID().toString(),
            correlationId == null || correlationId.isBlank() ? UUID.randomUUID().toString() : correlationId,
            Instant.now().toEpochMilli(), "data-service", "1.0.0", type, payload);
    }
}
