import os
import json
import random
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-default-secret-key')

# --- ユーティリティ関数 ---

def parse_student_data(data_string):
    """テキストエリアから貼り付けられた生徒データをパースする"""
    students = []
    lines = data_string.strip().split('\n')
    for i, line in enumerate(lines):
        parts = [p.strip() for p in line.replace('　', '\t').split('\t')]
        parts = [p for p in parts if p]
        if len(parts) >= 3:
            student = {
                'id': i + 1,
                'number': parts[0],
                'name': parts[1],
                'name_kana': parts[2],
                'name_en': parts[3] if len(parts) > 3 else ''
            }
            students.append(student)
    return students

def get_student_by_id(students, student_id):
    """IDから生徒情報を取得する"""
    if not students: return None
    for student in students:
        if student['id'] == student_id:
            return student
    return None

def get_neighbors(r, c, seat_map):
    """指定された座席の隣接（縦横斜め）の座席座標を返す"""
    neighbors = []
    for dr in [-1, 0, 1]:
        for dc in [-1, 0, 1]:
            if dr == 0 and dc == 0: continue
            nr, nc = r + dr, c + dc
            if (nr, nc) in seat_map:
                neighbors.append((nr, nc))
    return neighbors

# --- 席替えロジックの中核クラス ---
class SeatingArranger:
    def __init__(self, students, active_seats, constraints):
        self.students = students
        self.student_ids = {s['id'] for s in students}
        self.active_seats = active_seats
        self.constraints = constraints
        self.seat_map = {pos: None for pos in self.active_seats}

    def _evaluate(self, arrangement):
        """配置を評価し、違反点の合計を返す（低いほど良い）"""
        score = 0
        student_positions = {sid: pos for pos, sid in arrangement.items() if sid is not None}
        
        for pair in self.constraints.get('apart', []):
            if pair[0] in student_positions and pair[1] in student_positions:
                pos1, pos2 = student_positions[pair[0]], student_positions[pair[1]]
                if pos2 in get_neighbors(pos1[0], pos1[1], self.seat_map): score += 10
        
        for pair in self.constraints.get('together', []):
            if pair[0] in student_positions and pair[1] in student_positions:
                pos1, pos2 = student_positions[pair[0]], student_positions[pair[1]]
                if pos2 not in get_neighbors(pos1[0], pos1[1], self.seat_map): score += 10
        
        if self.active_seats:
            sorted_seats = sorted(list(self.active_seats))
            front_student_ids = self.constraints.get('front', [])
            num_front_students = len(front_student_ids)
            if num_front_students > 0:
                front_section_seats = set(sorted_seats[:num_front_students])
                for sid in front_student_ids:
                    if sid in student_positions and student_positions[sid] not in front_section_seats: score += 1

            back_student_ids = self.constraints.get('back', [])
            num_back_students = len(back_student_ids)
            if num_back_students > 0:
                back_section_seats = set(sorted_seats[-num_back_students:])
                for sid in back_student_ids:
                    if sid in student_positions and student_positions[sid] not in back_section_seats: score += 1
        return score

    def solve(self):
        """
        新しい手続き的アルゴリズムで配置を生成する。
        成功すれば配置を、失敗すればNoneを返す。
        """
        arrangement = {pos: None for pos in self.active_seats}
        placed_sids = set()

        # 1. 固定席を配置
        for item in self.constraints.get('fixed', []):
            sid, pos = item['student_id'], tuple(item['pos'])
            if pos in arrangement and arrangement[pos] is None and sid in self.student_ids:
                arrangement[pos] = sid
                placed_sids.add(sid)
            else: return None

        # 2. 最前列・最後列を配置
        sorted_seats = sorted(list(self.active_seats))
        
        front_sids = [sid for sid in self.constraints.get('front', []) if sid not in placed_sids and sid in self.student_ids]
        if front_sids:
            available_front = [s for s in sorted_seats[:len(front_sids)] if arrangement[s] is None]
            if len(available_front) < len(front_sids): return None
            random.shuffle(front_sids)
            for i, sid in enumerate(front_sids):
                arrangement[available_front[i]] = sid
                placed_sids.add(sid)

        back_sids = [sid for sid in self.constraints.get('back', []) if sid not in placed_sids and sid in self.student_ids]
        if back_sids:
            available_back = [s for s in sorted_seats[-len(back_sids):] if arrangement[s] is None]
            if len(available_back) < len(back_sids): return None
            random.shuffle(back_sids)
            for i, sid in enumerate(back_sids):
                arrangement[available_back[i]] = sid
                placed_sids.add(sid)
        
        # 3. くっつけたいペアを配置
        together_pairs = [p for p in self.constraints.get('together', []) if p[0] not in placed_sids and p[1] not in placed_sids and p[0] in self.student_ids and p[1] in self.student_ids]
        empty_seats = [pos for pos, sid in arrangement.items() if sid is None]
        random.shuffle(empty_seats)
        
        for pair in together_pairs:
            placed = False
            for seat1 in empty_seats:
                if arrangement[seat1] is None:
                    neighbors = get_neighbors(seat1[0], seat1[1], self.seat_map)
                    empty_neighbors = [n for n in neighbors if arrangement.get(n) is None]
                    if empty_neighbors:
                        seat2 = random.choice(empty_neighbors)
                        arrangement[seat1], arrangement[seat2] = pair[0], pair[1]
                        placed_sids.update(pair)
                        empty_seats.remove(seat1)
                        empty_seats.remove(seat2)
                        placed = True
                        break
            if not placed: return None

        # 4. 残りの生徒をランダムに配置
        remaining_sids = [sid for sid in self.student_ids if sid not in placed_sids]
        final_empty_seats = [pos for pos, sid in arrangement.items() if sid is None]
        if len(remaining_sids) != len(final_empty_seats): return None

        random.shuffle(remaining_sids)
        for i, seat in enumerate(final_empty_seats):
            arrangement[seat] = remaining_sids[i]

        # 5. 最終検証
        if self._evaluate(arrangement) == 0:
            return arrangement
        return None

    def generate_initial_arrangement(self):
        """ルーレット用の完全ランダム配置を生成する"""
        arrangement = {pos: None for pos in self.active_seats}
        students_to_place = [s['id'] for s in self.students]
        random.shuffle(students_to_place)
        empty_seats = list(self.active_seats)
        for i, seat in enumerate(empty_seats):
            if i < len(students_to_place):
                arrangement[seat] = students_to_place[i]
        return arrangement

# --- Flask ルート定義 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        student_data_str = request.form.get('student_data', '')
        session['students_original'] = parse_student_data(student_data_str)
        if not session['students_original']:
            return render_template('index.html', error="データを正しく読み込めませんでした。形式を確認してください。", show_teacher_warning=True)
        return redirect(url_for('step1_layout'))
    session.clear()
    return render_template('index.html', show_teacher_warning=True)

@app.route('/setup/step1_layout', methods=['GET', 'POST'])
def step1_layout():
    if 'students_original' not in session: return redirect(url_for('index'))
    if request.method == 'POST':
        session['active_seats'] = json.loads(request.form.get('layout_data'))
        return redirect(url_for('step2_secret_conditions'))
    return render_template('step1_layout.html', students=session['students_original'], show_teacher_warning=True)

@app.route('/setup/step2_secret_conditions', methods=['GET', 'POST'])
def step2_secret_conditions():
    if 'students_original' not in session: return redirect(url_for('index'))
    if request.method == 'POST':
        constraints = session.get('constraints', {})
        constraints.update({
            'apart': json.loads(request.form.get('apart_list', '[]')),
            'together': json.loads(request.form.get('together_list', '[]')),
            'secret_front': [int(sid) for sid in request.form.getlist('secret_front_row_list')],
            'secret_back': [int(sid) for sid in request.form.getlist('secret_back_row_list')],
        })
        session['constraints'] = constraints
        return redirect(url_for('step3_public_conditions'))
    
    return render_template('step2_secret_conditions.html', 
                           students=session['students_original'], 
                           constraints=session.get('constraints', {}),
                           show_teacher_warning=True)

@app.route('/setup/step3_public_conditions', methods=['GET', 'POST'])
def step3_public_conditions():
    if 'constraints' not in session: return redirect(url_for('index'))
    if request.method == 'POST':
        constraints = session.get('constraints', {})
        constraints.update({
            'public_front': [int(sid) for sid in request.form.getlist('public_front_row_list')],
            'public_back': [int(sid) for sid in request.form.getlist('public_back_row_list')],
            'fixed': json.loads(request.form.get('fixed_seat_list', '[]')),
            'exclude': [int(sid) for sid in request.form.getlist('exclude_list')],
        })
        session['constraints'] = constraints
        
        excluded_ids = set(constraints.get('exclude', []))
        students_needing_seats = [s for s in session['students_original'] if s['id'] not in excluded_ids]
        
        if len(session['active_seats']) < len(students_needing_seats):
            num_seats = len(session['active_seats'])
            num_students = len(students_needing_seats)
            error_msg = f"座席数は{num_seats}個、生徒数は{num_students}人で一致しません。座席指定をし直すか、除外生徒を選択してください。"
            return render_template('step3_public_conditions.html', 
                                   students=session['students_original'], 
                                   active_seats=session['active_seats'], 
                                   constraints=session.get('constraints', {}),
                                   error=error_msg)

        session['students'] = students_needing_seats
        return redirect(url_for('step4_roulette'))
    
    return render_template('step3_public_conditions.html', 
                           students=session['students_original'], 
                           active_seats=session['active_seats'], 
                           constraints=session.get('constraints', {}))

@app.route('/roulette')
def step4_roulette():
    if 'students' not in session: return redirect(url_for('index'))
    return render_template('step4_roulette.html')

@app.route('/manual')
def manual():
    """取扱説明書ページを表示する"""
    return render_template('manual.html')

def get_final_constraints():
    """セッションから最終的な制約を統合して返す"""
    final_constraints = session.get('constraints', {}).copy()
    secret_front = set(final_constraints.get('secret_front', []))
    public_front = set(final_constraints.get('public_front', []))
    final_constraints['front'] = list(secret_front | public_front)

    secret_back = set(final_constraints.get('secret_back', []))
    public_back = set(final_constraints.get('public_back', []))
    final_constraints['back'] = list(secret_back | public_back)
    return final_constraints

@app.route('/api/generate_arrangements')
def api_generate_arrangements():
    """席替え案を生成するAPI。新しい手続き的アルゴリズムを使用する。"""
    if 'students' not in session: return jsonify({"error": "No student data"}), 400
    
    students = session['students']
    active_seats = [tuple(p) for p in session['active_seats']]
    final_constraints = get_final_constraints()
    
    arranger = SeatingArranger(students, active_seats, final_constraints)
    
    solutions = []
    attempts = 0
    while len(solutions) < 5 and attempts < 500: # 5個の解を最大500回試行して見つける
        arrangement = arranger.solve()
        if arrangement and arrangement not in solutions:
            solutions.append(arrangement)
        attempts += 1
    
    if not solutions:
        return jsonify({
            "error": "条件を満たす席替え案を見つけられませんでした。条件が厳しすぎるか、矛盾している可能性があります。",
            "solutions": [], "randoms": []
        }), 400

    randoms_needed = 20 - len(solutions)
    randoms = [arranger.generate_initial_arrangement() for _ in range(randoms_needed)]
    
    solutions_json = [[{'pos': pos, 'student': get_student_by_id(students, sid)} for pos, sid in sol.items()] for sol in solutions]
    randoms_json = [[{'pos': pos, 'student': get_student_by_id(students, sid)} for pos, sid in rnd.items()] for rnd in randoms]
    
    return jsonify({'solutions': solutions_json, 'randoms': randoms_json})


@app.route('/ordered_arrangement', methods=['POST'])
def ordered_arrangement():
    """出席番号順の配置を生成する"""
    if 'constraints' not in session: return redirect(url_for('index'))
    
    constraints = session.get('constraints', {})
    constraints.update({
        'public_front': [int(sid) for sid in request.form.getlist('public_front_row_list')],
        'public_back': [int(sid) for sid in request.form.getlist('public_back_row_list')],
        'fixed': json.loads(request.form.get('fixed_seat_list', '[]')),
        'exclude': [int(sid) for sid in request.form.getlist('exclude_list')],
    })
    session['constraints'] = constraints
    final_constraints = get_final_constraints()

    excluded_ids = set(final_constraints.get('exclude', []))
    students_needing_seats = [s for s in session['students_original'] if s['id'] not in excluded_ids]
    
    if len(session['active_seats']) < len(students_needing_seats):
        num_seats, num_students = len(session['active_seats']), len(students_needing_seats)
        error_msg = f"座席数は{num_seats}個、生徒数は{num_students}人で一致しません。座席指定をし直すか、除外生徒を選択してください。"
        return render_template('step3_public_conditions.html', students=session['students_original'], active_seats=session['active_seats'], constraints=session.get('constraints', {}), error=error_msg)

    sorted_seats = sorted(session['active_seats'], key=lambda pos: (pos[1], pos[0]))
    sorted_students = sorted(students_needing_seats, key=lambda s: int(s['number']))

    front_sids, back_sids = set(final_constraints.get('front', [])), set(final_constraints.get('back', []))

    front_students = [s for s in sorted_students if s['id'] in front_sids]
    back_students = [s for s in sorted_students if s['id'] in back_sids]
    middle_students = [s for s in sorted_students if s['id'] not in front_sids and s['id'] not in back_sids]

    final_arrangement_dict = {}
    seat_idx = 0
    for student in front_students:
        final_arrangement_dict[tuple(sorted_seats[seat_idx])] = student
        seat_idx += 1
    for student in middle_students:
        final_arrangement_dict[tuple(sorted_seats[seat_idx])] = student
        seat_idx += 1
    back_students.reverse()
    for i, student in enumerate(back_students):
        final_arrangement_dict[tuple(sorted_seats[-(i+1)])] = student
    
    session['final_arrangement'] = [{'pos': pos, 'student': student} for pos, student in final_arrangement_dict.items()]
    
    return redirect(url_for('print_view'))


@app.route('/api/verify_arrangement')
def api_verify_arrangement():
    """最終配置が制約を満たしているか検証し、設定内容も返す"""
    if 'final_arrangement' not in session:
        # 印刷ページなどから戻ってきた時用に、セッションがクリアされていても
        # トップページに戻すように誘導する
        if 'students_original' not in session:
             return jsonify({"error": "No data", "redirect": url_for('index')}), 404
        else:
             return jsonify({"error": "Final arrangement not found"}), 404

    arrangement_list = session['final_arrangement']
    arrangement = {tuple(item['pos']): item['student'] for item in arrangement_list if item and item.get('pos') and item.get('student')}
    
    constraints = get_final_constraints()
    verification_results = {}
    all_students = session.get('students_original', [])

    for pos, student in arrangement.items():
        if not student: continue
        sid = student['id']
        messages, tags, status = [], [], 'ok'
        
        for f in constraints.get('fixed', []):
            if f['student_id'] == sid and tuple(f['pos']) == pos: messages.append('✅ 固定席')
        
        if sid in constraints.get('front', []):
             messages.append('✅ 最前列希望')
        
        if sid in constraints.get('back', []):
            messages.append('✅ 最後列希望')

        neighbor_sids = {arrangement[n_pos]['id'] for n_pos in get_neighbors(pos[0], pos[1], arrangement) if arrangement.get(n_pos)}

        for pair in constraints.get('together', []):
            if sid in pair:
                tags.append('together')
                other_sid = pair[0] if pair[1] == sid else pair[1]
                if other_sid in neighbor_sids: messages.append(f'💖 {get_student_by_id(all_students, other_sid)["name"]}と隣')
                else: messages.append(f'💔 {get_student_by_id(all_students, other_sid)["name"]}と離れている'); status = 'error'
        
        for pair in constraints.get('apart', []):
            if sid in pair:
                tags.append('apart')
                other_sid = pair[0] if pair[1] == sid else pair[1]
                if other_sid in neighbor_sids: messages.append(f'❌ {get_student_by_id(all_students, other_sid)["name"]}と隣'); status = 'error'

        verification_results[sid] = {'status': status, 'messages': messages, 'tags': tags}

    return jsonify({
        'arrangement': arrangement_list,
        'verification': verification_results,
        'constraints': constraints,
        'all_students': all_students
    })


@app.route('/print')
def print_view():
    if 'final_arrangement' not in session: return "最終結果がありません。席替えを実行してください。"
    arrangement_list = session['final_arrangement']
    final_arrangement = {tuple(item['pos']): item['student'] for item in arrangement_list if item and item.get('pos') and item.get('student')}
    rows = max(r for r, c in final_arrangement.keys()) + 1 if final_arrangement else 0
    cols = max(c for r, c in final_arrangement.keys()) + 1 if final_arrangement else 0
    today = datetime.now().strftime('%Y年%m月%d日')
    return render_template('print.html', arrangement=final_arrangement, rows=rows, cols=cols, date=today)

@app.route('/api/set_final_arrangement', methods=['POST'])
def set_final_arrangement():
    session['final_arrangement'] = request.get_json()['arrangement']
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

