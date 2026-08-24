FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY src src
RUN --mount=type=cache,target=/root/.m2,sharing=locked mvn -B package

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S app && adduser -S -G app app
WORKDIR /app
COPY --from=build /build/target/data-service-1.0.0.jar app.jar
USER app
EXPOSE 8000
ENTRYPOINT ["java","-XX:MaxRAMPercentage=75","-jar","app.jar"]
