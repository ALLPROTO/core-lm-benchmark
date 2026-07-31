# Known limitations

> Detailed development/provenance record. Historical version identifiers are
> retained for exact reproducibility. The concise end-user boundary is
> [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

1. Release-сборка записывает в подписанные resources абсолютный путь и
   детерминированный SHA-256-манифест полного base Python prefix, venv,
   `site-packages`, native-библиотек и symlink topology. Приложение
   fail-closed перепроверяет точный состав и каждый loadable-файл перед
   запуском. Volatile `__pycache__` исключён из манифеста, а worker запускается
   с `-B -X pycache_prefix=<private-empty-directory>`, поэтому эти `.pyc` не
   читаются и не записываются.
   Поэтому сборка аутентифицирует runtime, но остаётся привязана к машине и
   пути, на которых была упакована; это ещё не переносимый bundled runtime.
2. Репозиторий публикует исходники, а не переносимый готовый `.app`.
   Пользовательская сборка явно подписывается локально ad-hoc с hardened
   runtime и не требует Apple Developer Program. Такой bundle проверяем на
   машине, где он собран, но перенесённая копия не имеет доверия Gatekeeper
   как notarized Developer-ID binary.
3. Приложение не использует App Sandbox и запускает внешний Python с правами
   текущего пользователя. Подписанный манифест закрывает подмену runtime до
   старта worker, но внешний runtime всё равно принадлежит локальному
   пользователю и не устраняет гонку с изменением после preflight. Прототип
   предназначен только для доверенной локальной машины и проверенного offline
   model cache, а не для недоверенных моделей, датасетов или Python-пакетов.
4. Peak memory измеряется Python `tracemalloc` и не включает всю native-память
   NumPy.
5. Energy/CSI сравниваются на реконструированной траектории; это не
   task-level LLM quality.
6. Вывод доказан для размерностей 32, 96 и 256, указанных пяти входных
   сценариев и проверенных диапазонов параметров; он не переносится
   автоматически на любые данные.
7. Контрольный результат относится только к опубликованной реализации версии
   0.3.0, арифметике `fixed-order-f64-v1`, каноническому бинарному формату
   `voidtoken-residual-keyframe-v4` и зафиксированной матрице входов.
8. Отдельный real-LLM pilot относится только к pinned
   `Qwen/Qwen2.5-0.5B`, указанным блокам WikiText-2, teacher-forced replay и
   записанному Apple-Silicon/MPS runtime. Он не доказывает качество
   free-running generation, других моделей или production serving.
9. Real-LLM pilot дал отрицательный строгий вердикт обоим семействам:
   VoidToken существенно ухудшил NLL и top-1, а mixed group quant при 2.02×
   сохранил NLL, но достиг 97.95% top-1 вместо требуемых 99%.
10. PyTorch logits не обещаны побитно одинаковыми между MPS, CUDA и CPU.
   Точными остаются pins исходников, token/cache/container SHA-256 и
   внутренние layout/container round trips записанного запуска.
11. Первоначальный real-LLM pilot не имел независимой внешней временной метки
    до первого test-запуска. Его следует считать exploratory. Отдельный v5
    workflow использует публичные protocol/pretest/evidence tags, но Git tags
    и локальные marker-файлы всё равно не являются криптографически
    неизменяемым журналом.
12. Метрики VoidToken v5 на validation-блоках 0–31 использовались адаптивно
    для разработки и не являются prospective доказательством. One-shot
    selection на validation 32–63 и prospective holdout на test 384–415
    завершены с PASS по всем семи gates. Этот PASS относится только к
    зарегистрированному узкому scope и не превращает development-блоки в
    prospective evidence.
13. Локальный durable attempt marker предотвращает штатный retry после crash,
    но сам по себе не может криптографически доказать, что человек не удалял
    файл или не запускал изменённую копию. Нормативной считается первая
    публично зафиксированная попытка, включая incomplete marker.
14. Token-level Wilson bound использует коррелированные teacher-forced решения
    и не интерпретируется как независимая Bernoulli-выборка. Поэтому v5
    дополнительно требует Student-t lower bound по 32 block-level top-1 rates.
15. Reproducibility tar не содержит Git object database. В нём v5 verifier
    проверяет схемы, байты, SHA-256, связи marker/result и рекомпутацию метрик,
    но не Git tags и не публичную временную метку. Проверка Git-object и
    локальных tag targets требует клона репозитория с тегами и флага
    `--require-git-provenance`; публичная хронология проверяется отдельно по
    remote/GitHub record.
16. Development-shard содержат самодекларируемое
    `testDataOpened: false` и хеши промежуточных данных. Offline-проверка
    подтверждает их целостность и арифметику, но не может независимо доказать
    историю доступа исходного процесса к данным.
17. Проверяемый реальный прогон macOS-приложения на validation-блоках 64–71
    подтверждает интеграцию `.app` → внешний pinned Python runtime → Qwen/MPS
    → Swift verifier и точный v2 container accounting. Эти блоки являются
    раскрытым инженерным резервом, поэтому успешный прогон не считается новым
    prospective evidence. Во время MPS-прогона приложение блокирует idle sleep;
    явный Sleep, закрытие крышки или критический заряд всё ещё могут прервать
    выполнение, и такой незавершённый запуск не должен считаться evidence.
