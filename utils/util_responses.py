# utils/util_responses.py
from flask import jsonify

def success_response(data=None, message="操作成功"):
    """创建成功响应"""
    return jsonify({
        "success": True,
        "message": message,
        "data": data
    })

def error_response(message, status_code=400, details=None):
    """创建错误响应"""
    response = {
        "success": False,
        "error": {
            "code": status_code,
            "message": message,
            "details": details
        }
    }
    return jsonify(response), status_code