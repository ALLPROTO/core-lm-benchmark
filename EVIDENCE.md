# Core LM Compression Evidence

> Development and scientific provenance record. Historical version identifiers
> are intentional here. Ordinary users should start with
> [`README.md`](README.md) and [`docs/RESULTS.md`](docs/RESULTS.md).

Вердикт локального real-LLM application proof: **PASS**. Это regression
evidence на публичных validation-блоках, а не новый blind-результат.

Статус beacon-selected held-out эксперимента: **NOT STARTED**.

Проверено чистой production-сборкой Swift 6.3.3 и встроенной launch-only
проверкой:

- `.app` собран и ad-hoc подписан;
- создано одно видимое окно требуемого минимального размера;
- runtime error отсутствует.

Отдельно выполнен полный путь через этот же собранный `.app`. Приложение
запустило самостоятельный worker PID,
загрузило pinned `Qwen/Qwen2.5-0.5B` revision offline на MPS и проверило
возвращённый документ в Swift:

| Blocks | Container entries | Compression | ΔNLL | Top-1 | Scientific | Swift | Independent Python |
|---:|---:|---:|---:|---:|---|---|---|
| 8 | 192 | 2.052384× | −0.00000849 | 99.5117% | PASS | PASS | PASS |

Обезличенные result/receipt и byte-level checksums находятся в
`app-real-llm-evidence/`. Receipt связывает SHA-256 приложения, внешнего
runtime-манифеста, Python executable, runner resource и результата; абсолютные
пользовательские пути из него удалены. Команда
`python security/verify_app_run_evidence.py` проверяет неизменный исторический
result/receipt. Новый пользователь собирает другой бинарник; команда
`python security/verify_local_app_run.py --app dist/CoreLMBenchmark.app`
проверяет согласованность его ручного запуска, а `./run_local_app_proof.sh`
связывает receipt со случайным local challenge. Challenge защищает
trusted-local workflow от случайного выбора stale run, но не доказывает
криптографическую свежесть удалённому наблюдателю. SHA-256 нового
бинарника не должен совпадать со старым receipt. Это post-development
integration regression evidence на фиксированных публичных validation-блоках
64–71. Они многократно использовались, поэтому не являются blind-выборкой,
новым holdout или основанием для generalization claim. Три одинаковых
прогона проверяют repeatability одного workflow, а не являются тремя
независимыми экспериментами.

## Исторический non-model suite

Начальное исследование траекторий из 115 прогонов сохранено только как
архивный provenance. Оно не использовало LLM, не входит в нативное приложение
и не является доказательством компрессии Qwen. Точные источники и артефакты не
переписываются; их границы и хронология кратко описаны в
[`docs/development/HISTORY.md`](docs/development/HISTORY.md).

## Отдельный pilot на реальной LLM

Архивный non-model результат не переносится на learned KV-cache. Поэтому в
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
качества. Этот результат публикуется как отрицательный и не смешивается с
архивным trajectory suite.

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

## Следующий beacon-selected held-out эксперимент

Отдельные `RealLLM/BEACON_HELDOUT_PROTOCOL.md`,
`beacon_registration.json` и `beacon_window_ledger.json` фиксируют точные
параметры, gates, 15 допустимых test-окон и правило выбора по будущему NIST
Randomness Beacon. Freeze уже публичен: immutable release
`corelm-beacon-heldout-v1` опубликован `2026-08-01T01:18:09Z`, tag commit —
`0a9c0dd3ec6eee00d4029e6393e6f9fef96c5c44`, protocol commit —
`b34bc4d06c00c86b99076b117049e2d590d73bcd`. Первоначальный заголовок
`Normative files` над четырьмя пунктами был исправлен до pulse, в
`2026-08-01T10:08:12Z`, на `Key normative artifacts`; release notes теперь явно
ссылаются на полный авторитетный список из 26 записей в
`RealLLM/beacon_freeze.json`. Tag, assets, frozen files и первоначальный
`published_at` при notes-only исправлении не изменились.

Точный pulse — `2026-08-02T18:00:00.000Z`, deadline завершения —
`2026-08-04T18:00:00.000Z`. Разрешён один необратимый записанный запуск из
чистого detached checkout frozen tag без последующей подстройки. Все
сохранившиеся артефакты публикуются без изменений при `PASS`, `FAIL_GATES`,
`FAIL_EXECUTION` или `CONSUMED_INCOMPLETE`. Только после терминального `PASS`
или `FAIL_GATES` повтор публикуется как regression; `FAIL_EXECUTION` и
незавершённый attempt запрещают повторный запуск. Результата этого suite пока
нет, а блоки 64–71 для него исключены. Точный порядок действий закреплён в
`docs/BEACON_LAUNCH_RUNBOOK.md`.

Поскольку WikiText-2 публичен, корректное название — post-freeze
beacon-selected held-out-window evaluation, а не доказательство того, что
данные никто ранее не мог просмотреть или запустить приватно. Локальный attempt
marker — процедурный контроль, а не remote-attested доказательство отсутствия
тайных копий запуска.
