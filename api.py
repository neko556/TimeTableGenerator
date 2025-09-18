from flask import Flask, jsonify
from main import main, get_student_timetable, set_solved_result  # include set_solved_result

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "message": "Backend is running. Use /generate first, then /timetable/<student_id>."
    })

@app.route("/generate")
def generate_timetable():
    try:
        # Run solver and store the result globally in main.py
        result = main(json_output=True)
        set_solved_result(result)
        return jsonify({"message": "Timetable generated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/timetable/<student_id>")
def student_timetable(student_id):
    try:
        result = get_student_timetable(student_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/master")
def get_master_timetable():
    from main import SOLVED_RESULT
    if SOLVED_RESULT is None:
        return jsonify({"error": "No timetable generated yet. Call /generate first."}), 400
    return jsonify({"master_timetable": SOLVED_RESULT["records"]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
