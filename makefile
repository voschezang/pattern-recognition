PROJECT := pattern-recognition
LOG_DIR := /tmp/pattern-recognition_ml_models
# SHELL=/bin/bash
# SOURCE=$(shell bash -c ./setenv.sh)

.PHONY: logs test


start:
	jupyter notebook src/

# run:
# 	anaconda-project run


activate:
	bash -c "source setenv.sh; env | sed 's/=/:=/' | sed 's/^/export /' > makeenv"
	include makeenv
# bash setenv.sh

deps:
	conda install anaconda-project

test:
	pythonw src/test_import.py
# pythonw src/test_midi2.py

archive:
	anaconda-project archive $(PROJECT).zip

train:
	make clear-logs
	python3 src/main.py

logs:
	open http:localhost:6006
	tensorboard --logdir=$(LOG_DIR)

refresh-logs:
	make clear-logs
	make logs

save-logs:
	rm -rf logs/
	mkdir logs
	cp $(LOG_DIR)/* logs/

clear-logs:
	rm -rf $(LOG_DIR)/*

load-logs:
	cp logs/* $(LOG_DIR)/

ls:
	ls $(LOG_DIR)/

rm-env:
	conda env remove -n pattern_recognition

dialyzer:
	mypy src/test_midi.py

predict:
	python3 src/main.py $(book)

clean:
	find . -name \*.pyc -delete
