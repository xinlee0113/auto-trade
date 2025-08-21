.PHONY: help install install-dev test test-unit test-integration lint format clean docs run

# 默认目标
help:
	@echo "可用的命令:"
	@echo "  install       - 安装生产环境依赖"
	@echo "  install-dev   - 安装开发环境依赖"
	@echo "  test          - 运行所有测试"
	@echo "  test-unit     - 运行单元测试"
	@echo "  test-integration - 运行集成测试"
	@echo "  lint          - 运行代码检查"
	@echo "  format        - 格式化代码"
	@echo "  clean         - 清理临时文件"
	@echo "  docs          - 生成文档"
	@echo "  run           - 运行主程序"
	@echo "  demo          - 运行QQQ期权演示"

# 安装依赖
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

# 测试相关
test:
	pytest test/ -v --cov=src --cov-report=term-missing --cov-report=html

test-unit:
	pytest test/ -v -m "unit or not integration" --cov=src

test-integration:
	pytest test/ -v -m "integration" --cov=src

test-watch:
	pytest-watch test/ --cov=src

# 代码质量
lint:
	flake8 src test
	mypy src
	black --check src test
	isort --check-only src test

format:
	black src test
	isort src test

type-check:
	mypy src

# 清理
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

# 文档
docs:
	@echo "生成项目文档..."
	@echo "请查看 docs/ 目录中的文档文件"

# 运行程序
run:
	python main.py

demo:
	python demo_qqq_options.py

# 开发环境设置
setup-dev: install-dev
	pre-commit install

# 安全检查
security:
	bandit -r src/
	safety check

# 性能分析
profile:
	python -m cProfile -o profile.stats demo_qqq_options.py
	python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(20)"

# 代码复杂度分析
complexity:
	@echo "代码复杂度分析..."
	python -m mccabe --min 10 src/

# 依赖更新
update-deps:
	pip list --outdated
	@echo "运行 'pip install --upgrade <package>' 来更新特定包"

# Docker相关（如果需要）
docker-build:
	docker build -t auto-trade .

docker-run:
	docker run -it --rm auto-trade

# 发布相关
build:
	python -m build

upload-test:
	python -m twine upload --repository testpypi dist/*

upload:
	python -m twine upload dist/*
