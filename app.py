from flask import Flask, request, jsonify, render_template
import sqlalchemy
import logging
import pickle
import json
from sqlalchemy.sql import text

app = Flask(__name__)

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')

# 데이터베이스 연결 설정
DATABASE_URL = "postgresql://<user>:<password>@<host>/<database>"
engine = sqlalchemy.create_engine(DATABASE_URL)

def get_db_connection():
    """데이터베이스 연결을 생성하고 반환"""
    return engine.connect()

def get_component_info(componentid):
    """특정 componentid에 해당하는 부품 정보를 반환"""
    conn = get_db_connection()
    query = text("SELECT name, price, type FROM components WHERE componentid = :componentid")
    info = conn.execute(query, {"componentid": componentid}).fetchone()
    conn.close()
    return info

def get_random_components(type, count=5):
    """특정 타입의 부품을 랜덤하게 선택하여 반환"""
    conn = get_db_connection()
    query = text("SELECT componentid FROM components WHERE type = :type ORDER BY RANDOM() LIMIT :count")
    components = conn.execute(query, {"type": type, "count": count}).fetchall()
    conn.close()
    return components

# 모델과 라벨 인코더 로드
with open('pc_build_model.pkl', 'rb') as f:
    model, le_dict = pickle.load(f)

def recommend_components(budget):
    """사용자의 예산에 맞춰 부품을 추천하는 함수"""
    components = ["CPU", "GPU", "RAM", "Storage", "PSU", "Case", "Motherboard"]
    recommendation = {}
    total_price = 0
    complete = False

    while not complete:
        recommendation = {}
        total_price = 0
        try:
            input_data = [0] * len(components)
            for i, component in enumerate(components):
                random_components = get_random_components(component)
                for comp in random_components:
                    info = get_component_info(comp[0])
                    if info and total_price + float(info[1]) <= budget:
                        try:
                            encoded_value = le_dict[component].transform([str(comp[0])])[0]
                            if encoded_value in le_dict[component].classes_:
                                input_data[i] = encoded_value
                                total_price += float(info[1])
                                break
                        except ValueError as e:
                            logging.error(e)
                            continue

            # 예산 내에서 부품을 찾지 못할 경우 예외 처리
            for i, component in enumerate(components):
                if input_data[i] not in le_dict[component].classes_:
                    raise ValueError(f"Unseen label {input_data[i]} for component {component}")

            predicted_index = model.predict([input_data])[0]
            total_price = 0
            for i, component in enumerate(components):
                component_id = le_dict[component].inverse_transform([input_data[i]])[0]
                info = get_component_info(component_id)
                if info:
                    name, price, type_ = info
                    recommendation[component] = {"name": name, "price": float(price), "id": component_id}
                    total_price += float(price)

            if total_price > budget:
                raise ValueError("Total price exceeds budget")

            if len(recommendation) == 7:
                complete = True

            recommendation["Total Price"] = total_price
            logging.debug(f"Recommendation: {recommendation}")
        except Exception as e:
            logging.error(f"Error: {e}")
            recommendation = {}
            total_price = 0
            for component in components:
                random_components = get_random_components(component)
                selected_component = None
                max_price_within_budget = 0
                for comp in random_components:
                    info = get_component_info(comp[0])
                    if info and total_price + float(info[1]) <= budget and float(info[1]) > max_price_within_budget:
                        selected_component = comp
                        max_price_within_budget = float(info[1])
                if selected_component:
                    info = get_component_info(selected_component[0])
                    name, price, type_ = info
                    recommendation[component] = {"name": name, "price": float(price), "id": selected_component[0]}
                    total_price += float(price)

            if len(recommendation) == 7:
                complete = True

            recommendation["Total Price"] = total_price
            logging.debug(f"Fallback Recommendation: {recommendation}")

    return recommendation

def save_confirmed_quote(components):
    """확정된 견적을 데이터베이스에 저장하고 견적 ID를 반환"""
    conn = get_db_connection()
    query = text("INSERT INTO confirmed_quotes (components) VALUES (:components) RETURNING quoteid")
    quoteid = conn.execute(query, {"components": json.dumps(components)}).fetchone()[0]
    conn.close()
    return quoteid

@app.route('/')
def index():
    """홈페이지 렌더링"""
    return render_template('index.html')

@app.route('/recommend', methods=['POST'])
def recommend():
    """추천 요청을 처리하여 부품 조합을 반환"""
    data = request.json
    budget = data['budget']

    logging.debug(f"Budget: {budget}")

    recommendation = recommend_components(budget)
    return jsonify(recommendation)

@app.route('/confirm', methods=['POST'])
def confirm_quote():
    """사용자가 선택한 부품 조합을 확정하고 데이터베이스에 저장"""
    components = request.json
    quoteid = save_confirmed_quote(components)
    return jsonify({"quoteid": quoteid, "status": "confirmed"})

@app.route('/recommend_component', methods=['GET'])
def recommend_component():
    """사용자가 부품을 교체할 때 새로운 부품을 추천"""
    component_type = request.args.get('type')
    budget = float(request.args.get('budget'))
    
    if not component_type:
        return jsonify({"error": "Component type is required"}), 400
    
    random_components = get_random_components(component_type)
    selected_component = None
    max_price_within_budget = 0
    
    for comp in random_components:
        info = get_component_info(comp[0])
        if info and float(info[1]) <= budget and float(info[1]) > max_price_within_budget:
            selected_component = comp
            max_price_within_budget = float(info[1])
    
    if selected_component:
        info = get_component_info(selected_component[0])
        name, price, type_ = info
        component = {"name": name, "price": float(price), "id": selected_component[0]}
        return jsonify({component_type: component})
    else:
        return jsonify({"error": "No suitable component found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
