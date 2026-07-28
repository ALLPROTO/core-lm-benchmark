# Architecture

```text
RunConfiguration → DeterministicInputGenerator → materialized U_t
                                               ↓
                                          CoreLMAdapter
                                               ↓
                                         Dense trajectory
                                  ┌────────────┼────────────┐
                               Dense          PCA       VoidToken
                                  └────────────┼────────────┘
                                         MetricsCollector
                                               ↓
                                      Invariant + Verdict
                                      ↙                 ↘
                                 JSON/Markdown       SwiftUI
```

`BenchmarkCore` не зависит от UI. SwiftUI запускает CLI и отображает только
фактический сохранённый результат. Все методы получают одну плотную траекторию,
построенную из одного материализованного потока `U_t`.

VoidToken v3 использует closed-loop prediction:

1. Энкодер вычисляет residual относительно состояния, реально известного
   декодеру.
2. Кодирует top-k компонент residual.
3. Сразу локально декодирует токен и использует восстановленное состояние для
   следующего шага.
4. Автоматически выбирает интервал dense keyframes из байтового бюджета,
   сохраняя запас над целевыми 4×.

Поэтому отброшенная компонента возвращается в следующий residual, а ошибка не
накапливается бесконтрольно. Размер payload считается по реально сформированному
бинарному буферу, включая keyframes.
