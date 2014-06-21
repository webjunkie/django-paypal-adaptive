#!/bin/bash

find . -type f \( -name "*.pyc" -o -name "*~" \) -exec rm {} \;

