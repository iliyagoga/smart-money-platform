FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY src src
RUN mvn -B package

FROM eclipse-temurin:21-jre-alpine-3.23
RUN addgroup -S app && adduser -S -G app app
WORKDIR /app
COPY --from=build /build/target/data-service-1.0.0.jar app.jar
USER app
EXPOSE 8000
ENTRYPOINT ["java","-XX:MaxRAMPercentage=75","-jar","app.jar"]
