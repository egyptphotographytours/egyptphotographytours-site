name: Smart Meta NLLB Auto-Translation

on:
  push:
    branches: [ main ] 

jobs:
  translate:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        lang: [es, fr, de, it, pt, ru, ja, zh-CN, ko, ar, hi, nl, sv, pl, tr, vi, th, id, cs, ro, tl, no, da, fi]
    
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 2 

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Cache AI Model
        uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: hf-nllb-600m-${{ runner.os }}

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install torch --index-url https://download.pytorch.org/whl/cpu
          pip install transformers beautifulsoup4

      - name: Run Smart AI Translation Script
        env:
          TARGET_LANG: ${{ matrix.lang }}
        run: python translate_nllb.py

      - name: Commit and Push Translations (With Retry Logic)
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add ./${{ matrix.lang }}/
          git commit -m "chore: auto-translate to ${{ matrix.lang }}" || echo "No changes to commit"
          
          # 🛡️ RETRY LOOP: Prevents "Exit Code 1" crash when 24 languages push at the exact same second
          for i in {1..5}; do
            git push && break
            echo "⚠️ Push failed (likely a race condition). Pulling rebase and retrying in 5 seconds..."
            git pull --rebase
            sleep 5
          done
