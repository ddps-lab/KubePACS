import datetime
import os
import pandas as pd
import pytz

csv_dir = os.path.dirname(os.path.abspath(__file__))
csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]

dfs = []
for csv_file in csv_files:
    file_path = os.path.join(csv_dir, csv_file)
    try:
        df = pd.read_csv(file_path)
        
        df["first_time"] = pd.to_datetime(df["first_time"])
        df = df[df["first_time"] > datetime.datetime(2025, 5, 22, 8, 0, 0, tzinfo=pytz.timezone('Asia/Seoul'))]
        df.sort_values(by=["pods", "cpu", "memory", "first_time"], ascending=True, inplace=True, ignore_index=True)
        
        print(df.head())
        df.to_csv(csv_dir+f"/filtered_{csv_file}", index=False)
        print(f"{csv_file} 적재 완료 (행 수: {len(df)})")
    except Exception as e:
        print(f"{csv_file} 적재 실패: {e}")

# 모든 DataFrame은 dfs 리스트에 저장됨
