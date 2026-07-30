# Core LM Compression Evidence

Вердикт компрессии: **PASS**.

Вердикт готовности macOS-прототипа: **PASS**.

Проверено чистой production-сборкой Swift 6.3.3 и встроенным smoke-run:

- `.app` собран и ad-hoc подписан;
- создано одно видимое окно требуемого минимального размера;
- приложение через `BenchmarkStore` запустило реальное Python-ядро;
- получен PASS-прогон `c6cf776fc470cde2`;
- deterministic replay = true;
- runtime error отсутствует.

Отдельно выполнен реальный путь через этот же собранный `.app`, а не только
синтетический smoke-run. Приложение запустило самостоятельный worker PID,
загрузило pinned `Qwen/Qwen2.5-0.5B` revision offline на MPS и проверило
возвращённый документ в Swift:

| Blocks | Container entries | Compression | ΔNLL | Top-1 | Scientific | Swift | Independent Python |
|---:|---:|---:|---:|---:|---|---|---|
| 8 | 192 | 2.052384× | −0.00000849 | 99.5117% | PASS | PASS | PASS |

Обезличенные result/receipt и byte-level checksums находятся в
`app-real-llm-evidence/`. Receipt связывает SHA-256 приложения, внешнего
runtime-манифеста, Python executable, runner resource и результата; абсолютные
пользовательские пути из него удалены. Команда
`python security/verify_app_run_evidence.py --app dist/CoreLMBenchmark.app`
проверяет всю связь. Это post-development integration evidence на
validation-блоках 64–71, а не новый preregistered holdout и не расширение
исторического prospective claim.

## Полный suite

Выполнено 115 реальных прогонов:

- 3 размерности: 32, 96, 256;
- 5 seed: 7, 17, 42, 101, 997;
- 5 входных сценариев;
- 200 и 5000 шагов;
- top-k: 4, 8, 16;
- qmax: 127, 32767.

| Runs | PASS | FAIL | Minimum ratio | Worst NRMSE | Minimum cosine | Worst energy drift |
|---:|---:|---:|---:|---:|---:|---:|
| 115 | 115 | 0 | 4.2353× | 0.06089 | 0.99821 | 0.04955 |

Все 115 прогонов, включая все ненулевые сценарии, одновременно прошли четыре
порога качества и компрессии.

| Scenario | Runs | PASS | Worst NRMSE | Min cosine | Worst energy drift |
|---|---:|---:|---:|---:|---:|
| zero | 18 | 18 | 0.00000 | 1.00000 | 0.00000 |
| Gaussian bounded | 43 | 43 | 0.06089 | 0.99821 | 0.02545 |
| uniform bounded | 18 | 18 | 0.05191 | 0.99870 | 0.02257 |
| impulse | 18 | 18 | 0.05647 | 0.99865 | 0.04955 |
| repeating structured | 18 | 18 | 0.04606 | 0.99898 | 0.02085 |

Свежий полный replay автоматически сверяется с зарегистрированными run ID,
input digest, конфигурациями, инвариантами, научными метриками, time series и
aggregate. Нестабильные wall-clock timestamps, timings и platform memory в
научное сравнение не входят. Run ID, конфигурации, input digest, Core state
SHA-256, VoidToken payload/container SHA-256, SHA-256 восстановленной
VoidToken-траектории, инварианты и вердикты должны совпадать точно. Для числовой
диагностики PCA явно задан межплатформенный допуск `rtol=1e-4`, `atol=1e-5`;
он не может скрыть иной Core/VoidToken byte stream или иной результат
декодирования.

## Бинарный round trip

- Dense, PCA и VoidToken имеют самостоятельные decoder-функции.
- `fileBytes` равен фактической длине контейнера `CLMB`.
- VoidToken reconstruction строится разбором бинарного payload, а не
  вспомогательными объектами энкодера.
- Алгоритм VoidToken v3 записывается в канонический бинарный формат v4; прежний
  формат v3 читается отдельной legacy-веткой, а старый reader не принимает v4.
- Тесты проверяют `serialize -> parse -> decode`, keyframes, обрезанные данные,
  неверные индексы, NaN/Inf, диапазон quantized values и лишние байты.

## Исправленная причина

Версия v1 кодировала `S_t - S_(t-1)` относительно плотного состояния, которого
декодер не имел. Потери каждой дельты поэтому складывались.

Версия v3 кодирует `S_t - Ŝ_(t-1)`, где `Ŝ_(t-1)` — фактически восстановленное
состояние. Потерянная координата остаётся в следующем residual. Адаптивные
keyframes дополнительно ограничивают ошибку, а их интервал выбирается из
реального байтового бюджета.

## Пороги отдельного прогона

- VoidToken compression ≥ 4×;
- NRMSE ≤ 0.10;
- cosine ≥ 0.95;
- mean energy drift ≤ 5%;
- invariant violations = 0;
- deterministic replay = true.

## Границы вывода

Результат относится к алгоритму VoidToken residual-keyframe v3, его
каноническому бинарному формату v4 и проверенной матрице. Он доказывает
выполнение заданных критериев в этой области, но не является универсальной
гарантией для любых распределений и размерностей.

## Отдельный pilot на реальной LLM

Синтетический вердикт выше не переносится на learned KV-cache. Поэтому в
`real-llm-results/aggregate.json` отдельно записан exploratory-эксперимент на
настоящей pretrained-модели `Qwen/Qwen2.5-0.5B`: 24 слоя KV-cache,
WikiText-2, 8 test-блоков и 1024 next-token prediction.

| Семейство | Сжатие к BF16 | ΔNLL | Top-1 | Вердикт |
|---|---:|---:|---:|---|
| VoidToken v4 | 2.4184× | +0.203580 | 79.88% | **FAIL** |
| Mixed group quant baseline | 2.0214× | +0.001356 | 97.95% | **FAIL** |

Runner использует фиксированные пороги: сжатие не менее 2×, ΔNLL не более
0.01 nat/token и top-1 agreement не менее 99%. Pilot не был независимо
предзарегистрирован или externally timestamped до первого test. Baseline
прошёл первые два порога, но не прошёл top-1; VoidToken не прошёл оба порога
качества. Этот результат публикуется как отрицательный и не смешивается с 115
синтетическими PASS.

Для каждого блока прямой исходный `DynamicCache` и его flatten/rebuild копия
дали нулевую максимальную разницу logits. В модель подавался результат нового
разбора фактического бинарного контейнера, а не объект энкодера в памяти.

## Проспективный VoidToken v5 — финальный PASS

Отрицательный pilot выше не перезаписан. Записанный development-процесс
VoidToken v5 использовал validation-блоки 0–31. Инженерное наблюдение:
2.055836× полного container compression, ΔNLL +0.000804, top-1 99.5605%,
односторонняя 95% верхняя граница ΔNLL +0.001378 и block-aware нижняя граница
top-1 99.3638%.

Эти development-числа сами по себе не являются prospective PASS.
Конфигурация, 32 новых validation-блока, 32 disjoint test-блока,
статистические gates, runtime и код были зафиксированы в
`RealLLM/v5_registration.json` и опубликованы под
`voidtoken-v5-selection-protocol-v1` до one-shot selection.

Selection на validation-блоках 32–63 завершился PASS: 2.054320×, ΔNLL
+0.000573, односторонняя 95% верхняя граница ΔNLL +0.001222, top-1
4072/4096 = 99.4141% и Wilson lower95 99.1827%. Его неизменённые result и
attempt marker были опубликованы под `voidtoken-v5-pretest-v1` на commit
`34fbd0556bd4e8fb889e628ae35175ff596818af` до первого доступа v5 runner к
test split.

Зафиксированная one-shot попытка prospective holdout на test-блоках 384–415
из точного публичного pretest tag завершилась PASS: 2.053291×, ΔNLL −0.000061,
односторонняя 95% верхняя граница ΔNLL +0.000549, top-1 4071/4096 =
99.3896%, blockwise lower95 99.2472%, Wilson lower95 99.1543% и mean KL
0.00013431 nat. Все семь зарегистрированных gates истинны. Канонический
result SHA-256:
`d1c16e88655c1fbc9884324742dee3f0b9b4bc86d973c2bf38df3a02cc090eaa`.
Финальный evidence tag `voidtoken-v5-evidence-v1` указывает на commit
`531e4ab8d1de61ce93e83164d13caff7bb0759bc`. Отдельные исходники статьи и
проверенный PDF находятся в `publication/arxiv-v5/` и
`publication/corelm_voidtoken_v5.pdf`.

Точные `holdout.attempt.json` и `holdout.json` опубликованы в
`real-llm-v5-results/`; их file SHA-256 равны
`7f6bc0867db1e3d633c3ecb68aa968be94c73c818b2a5163793495cfb63c17a0` и
`499c067d6ccff4bf1ac4a9f98436a52fa6c414ccced495719532347b89b46167`.
Обе уже исчерпанные фазы записаны в historical v1 format, где нет
24-слойного `containerManifest`. Поэтому их container totals и compression
gate защищены неизменяемыми result/file SHA-256, execution commits и Git tags,
но являются **runner-recorded, а не независимо восстановленными по слоям**.
Перезапуск или переписывание one-shot артефактов нарушило бы протокол.
Verifier допускает v1 только по точному allowlist всех исторических digests и
provenance; любая мутация отвергается. Метрики качества, агрегаты, confidence
bounds и gate arithmetic всё ещё независимо пересчитываются. Полностью
независимый per-layer compression claim требует отдельного будущего v2 suite.
Команда
`python RealLLM/verify_voidtoken_v5_evidence.py --require-git-provenance`
проверяет обе фазы, marker/result links, Git tags, исходные digests, метрики,
confidence bounds, gates и финальный verdict.

Точные четыре development-shard, их диапазоны, file/result SHA-256 и
объединённая рекомпутация опубликованы в
`real-llm-v5-development/manifest.json`. Команда
`python RealLLM/verify_voidtoken_v5_development.py` проверяет их без модели и
датасета. Это доказывает целостность и арифметическую воспроизводимость
записанных артефактов, но не превращает адаптивную разработку в prospective
evidence. Финальный PASS ограничен закреплёнными Qwen revision, WikiText-2
окнами, MPS runtime и teacher-forced replay. Исторический compression ratio
сохраняется как integrity-protected runner-recorded measurement с описанным
выше ограничением, а не как независимо восстановленный container byte
accounting; это также не универсальное утверждение о других моделях или
production latency.
