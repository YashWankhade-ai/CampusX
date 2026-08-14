from flask import jsonify

def success_response(data=None, meta=None, message="Success", status_code=200, request_id=None):
    response = {
        "success": True,
        "message": message,
        "data": data if data is not None else {},
        "meta": meta if meta is not None else {},
        "error": None,
        "request_id": request_id
    }
    return jsonify(response), status_code

def error_response(message="Error", error_details=None, status_code=400, request_id=None, code=None):
    err_dict = {"code": code or "ERROR", "message": message}
    if error_details:
        err_dict["details"] = error_details

    response = {
        "success": False,
        "message": message,
        "data": None,
        "meta": None,
        "error": err_dict,
        "request_id": request_id
    }
    return jsonify(response), status_code
