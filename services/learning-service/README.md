# Learning Service

Непрерывно формирует обучающие примеры из `position.closed`, обновляет Thompson Sampling и обучает версионируемую LOGREG-модель с walk-forward проверкой. Метаданные хранятся в TimescaleDB, активная версия и предпочтения — в Redis, артефакты — в MinIO.

API: `/learning/samples`, `/learning/models`, `/learning/bandit`, `/learning/feature-importance`, `POST /learning/train`. Порт: `8060`.
