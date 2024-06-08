import pandas as pd
import sqlalchemy
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
import pickle
import json

# 데이터베이스 연결 설정
# DATABASE_URL = 개인정보
DATABASE_URL = "postgresql://<user>:<password>@<host>/<database>"
engine = sqlalchemy.create_engine(DATABASE_URL)

def get_db_connection():
    """데이터베이스 연결을 생성하고 반환"""
    return engine.connect()

def load_data():
    """데이터베이스에서 확정된 견적 데이터를 불러와서 DataFrame으로 반환"""
    conn = get_db_connection()
    query = "SELECT * FROM confirmed_quotes"
    df = pd.read_sql(query, conn)  # 확정된 견적 데이터를 DataFrame으로 로드
    conn.close()
    return df

def train_model():
    """확정된 견적 데이터를 이용하여 AI 모델을 학습하고 저장"""
    df = load_data()  # 데이터 로드
    # JSON 형식의 부품 데이터를 개별 컬럼으로 변환
    df['components'] = df['components'].apply(json.loads)
    components_df = df['components'].apply(pd.Series)

    # 각 부품의 ID를 레이블 인코딩
    le_dict = {}
    for column in components_df.columns:
        le = LabelEncoder()
        components_df[column] = le.fit_transform(components_df[column].astype(str))
        le_dict[column] = le

    # 특징과 타겟 변수 설정
    X = components_df.values  # 특징 행렬
    y = df.index  # 타겟 변수 (각 견적의 인덱스를 타겟으로 사용)

    # 랜덤 포레스트 모델 학습
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 학습된 모델과 라벨 인코더 딕셔너리를 파일로 저장
    with open('pc_build_model.pkl', 'wb') as f:
        pickle.dump((model, le_dict), f)

if __name__ == "__main__":
    train_model()  # 메인 함수 실행
