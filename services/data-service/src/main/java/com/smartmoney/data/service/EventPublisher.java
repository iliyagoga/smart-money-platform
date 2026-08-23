package com.smartmoney.data.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartmoney.data.model.EventEnvelope;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class EventPublisher {
    private final StringRedisTemplate redis;
    private final ObjectMapper json;
    public EventPublisher(StringRedisTemplate redis, ObjectMapper json) { this.redis = redis; this.json = json; }
    public void publish(String topic, Object payload, String correlationId) {
        try { redis.convertAndSend(topic, json.writeValueAsString(EventEnvelope.of(topic, payload, correlationId))); }
        catch (JsonProcessingException e) { throw new IllegalStateException("Cannot serialize event " + topic, e); }
    }
}
