# Colab 실행 순서

## 1. ZIP 업로드와 압축 해제
```python
from google.colab import files
import zipfile

uploaded = files.upload()
zip_name = next(iter(uploaded))
with zipfile.ZipFile(zip_name) as z:
    z.extractall('/content')
```

## 2. DB를 Google Drive에 영구 보관
```python
from google.colab import drive
from pathlib import Path
import os

drive.mount('/content/drive')
db_dir = Path('/content/drive/MyDrive/cam_icu_rass_v2_data')
db_dir.mkdir(parents=True, exist_ok=True)
os.environ['CAM_ICU_DB_PATH'] = str(db_dir / 'cam_icu.db')
os.environ['SECRET_KEY'] = '원하는-긴-임의문자열'
```

## 3. 앱과 공개 링크 실행
```python
%run /content/cam_icu_rass_v2/colab_start.py
```

출력된 `trycloudflare.com` 주소로 접속합니다. Colab 런타임이 종료되면 링크는 꺼지지만, 평가 데이터는 Google Drive의 DB에 남습니다. 다음 실행 때 1~3단계를 반복하면 같은 데이터가 연결됩니다.

## 주의
- `colab_start.py`는 한 런타임에서 한 번만 실행합니다.
- 코드 수정 후에는 서버를 재시작해야 반영됩니다.
- 영구적으로 켜진 주소가 필요하면 Render 등 별도 서버에 배포해야 합니다.
