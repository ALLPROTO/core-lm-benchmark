# Known limitations

1. Приложение ожидает доступный Python 3 с NumPy; путь можно задать через
   `PYTHON_BIN`, либо используется pyenv, Homebrew или `/usr/local`.
2. `.app` подписан ad-hoc, но не подписан Apple Developer ID и не notarized.
3. Peak memory измеряется Python `tracemalloc` и не включает всю native-память
   NumPy.
4. Energy/CSI сравниваются на реконструированной траектории; это не
   task-level LLM quality.
5. Вывод доказан для размерностей 32, 96 и 256, указанных пяти входных
   сценариев и проверенных диапазонов параметров; он не переносится
   автоматически на любые данные.
6. Контрольный результат относится только к опубликованной реализации версии
   0.3.0, арифметике `fixed-order-f64-v1`, каноническому бинарному формату
   `voidtoken-residual-keyframe-v4` и зафиксированной матрице входов.
7. Отдельный real-LLM pilot относится только к pinned
   `Qwen/Qwen2.5-0.5B`, указанным блокам WikiText-2, teacher-forced replay и
   записанному Apple-Silicon/MPS runtime. Он не доказывает качество
   free-running generation, других моделей или production serving.
8. Real-LLM pilot дал отрицательный строгий вердикт обоим семействам:
   VoidToken существенно ухудшил NLL и top-1, а mixed group quant при 2.02×
   сохранил NLL, но достиг 97.95% top-1 вместо требуемых 99%.
9. PyTorch logits не обещаны побитно одинаковыми между MPS, CUDA и CPU.
   Точными остаются pins исходников, token/cache/container SHA-256 и
   внутренние layout/container round trips записанного запуска.
10. Real-LLM протокол не имел независимой внешней временной метки до первого
    test-запуска. Validation и test разделены, однако pilot следует считать
    exploratory, а не строго preregistered исследованием.
