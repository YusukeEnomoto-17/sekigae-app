import os
import csv
import io
import random
from flask import Flask, render_template, request, redirect, url_for, session, send_file

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # セッション情報の暗号化キー（適宜変更してください）

@app.route('/', methods=['GET', 'POST'])
def index():
    # セッションの初期化（必要に応じて）
    if 'students' not in session:
        session['students'] = []
    
    if request.method == 'POST':
        # ファイルアップロードか手動入力か
        if 'file' in request.files and request.files['file'].filename != '':
            return upload_file()
        elif 'add_student' in request.form:
            return manual_input()
        elif 'clear_data' in request.form:
            session.pop('students', None)
            session.pop('current_layout', None)
            session.pop('final_layout', None)
            return redirect(url_for('index'))
        elif 'next_step' in request.form:
            # 生徒数が0でなければ次へ
            if len(session.get('students', [])) > 0:
                return redirect(url_for('step1_layout'))
            else:
                return render_template('index.html', students=[], error="生徒データがありません。")

    return render_template('index.html', students=session.get('students', []))

def upload_file():
    file = request.files['file']
    if not file:
        return redirect(url_for('index'))
    
    # CSVファイルを読み込む
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        students = session.get('students', [])
        
        for row in csv_input:
            # CSVのカラム名に依存。number, name, gender, group などを想定
            students.append({
                "number": row.get('number', ''),
                "name": row.get('name', ''),
                "gender": row.get('gender', 'unknown'),
                "group": row.get('group', '')
            })
        session['students'] = students
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return render_template('index.html', students=session.get('students', []), error="CSVファイルの読み込みに失敗しました。")
        
    return redirect(url_for('index'))

def manual_input():
    number = request.form.get('number')
    name = request.form.get('name')
    gender = request.form.get('gender')
    
    if name:
        students = session.get('students', [])
        students.append({
            "number": number,
            "name": name,
            "gender": gender,
            "group": None
        })
        session['students'] = students
    
    return redirect(url_for('index'))

@app.route('/step1_layout', methods=['GET', 'POST'])
def step1_layout():
    if request.method == 'POST':
        try:
            rows = int(request.form.get('rows'))
            cols = int(request.form.get('cols'))
            session['rows'] = rows
            session['cols'] = cols
            return redirect(url_for('step2_secret_conditions'))
        except ValueError:
            return render_template('step1_layout.html', error="行と列には数値を入力してください。")
            
    return render_template('step1_layout.html')

@app.route('/step2_secret_conditions', methods=['GET', 'POST'])
def step2_secret_conditions():
    if request.method == 'POST':
        # 秘密の条件（隣席禁止など）の保存処理（今回はUIのみでロジック未実装とする場合が多いが枠だけ用意）
        # session['secret_conditions'] = ...
        return redirect(url_for('step3_public_conditions'))
    return render_template('step2_secret_conditions.html', students=session.get('students', []))

@app.route('/step3_public_conditions', methods=['GET', 'POST'])
def step3_public_conditions():
    if request.method == 'POST':
        # 公開条件（前方希望など）の保存
        # session['public_conditions'] = ...
        return redirect(url_for('step4_roulette'))
    return render_template('step3_public_conditions.html', students=session.get('students', []))

@app.route('/step4_roulette', methods=['GET', 'POST'])
def step4_roulette():
    rows = session.get('rows', 6)
    cols = session.get('cols', 6)
    students = session.get('students', [])
    
    current_layout = session.get('current_layout')
    
    if request.method == 'POST':
        if 'start_roulette' in request.form:
            # 単純なランダム配置ロジック
            shuffled_students = students.copy()
            random.shuffle(shuffled_students)
            
            current_layout = [[None for _ in range(cols)] for _ in range(rows)]
            
            student_idx = 0
            for r in range(rows):
                for c in range(cols):
                    # ここで座席配置ロジック（本来は除外席などを考慮）
                    if student_idx < len(shuffled_students):
                        # 【変更点】名前の文字列だけではなく、辞書オブジェクトごと格納する
                        current_layout[r][c] = shuffled_students[student_idx]
                        student_idx += 1
            
            session['current_layout'] = current_layout
            
        elif 'confirm_layout' in request.form:
            session['final_layout'] = session.get('current_layout')
            return redirect(url_for('print_layout'))
            
    return render_template('step4_roulette.html', layout=current_layout, rows=rows, cols=cols)

@app.route('/print')
def print_layout():
    if 'final_layout' not in session:
        return redirect(url_for('index'))
    
    layout = session['final_layout']
    return render_template('print.html', layout=layout)

if __name__ == '__main__':
    app.run(debug=True)
