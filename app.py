"""
A sample Hello World server.
"""
from datetime import datetime
import os
from pathlib import Path
import shutil
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
import utilities as utilities
import gemini_functions as gf
import authentication as authentication
from dotenv import load_dotenv
import time
from google.cloud import logging

load_dotenv()

SOURCE_BUCKET = os.environ.get("SOURCE_BUCKET")
DESTINATION_BUCKET = os.environ.get("DESTINATION_BUCKET")
OCR_BUCKET = os.environ.get("OCR_BUCKET")
SECRET_KEY = os.environ.get("SECRET_KEY")
PROJECT_ID = os.environ.get("PROJECT_ID")

logging_client = logging.Client(project=PROJECT_ID)
log_name = "ezycontract_logs"
logger = logging_client.logger(log_name)
rag_db = None

# pylint: disable=C0103
app = Flask(__name__)
# Secret Key is used for session security.
app.secret_key = SECRET_KEY

@app.route('/contractupload')
def contractupload():
     # Check if user is logged in
    if session.get("is_logged_in", False):
        files_list = utilities.get_files_list(SOURCE_BUCKET)
        return render_template("ContractUpload.html",files_list=files_list)
    else:
        # If user is not logged in, redirect to login page
        return redirect(url_for('landing'))
    
@app.route('/contracthighlight')
def contracthighlight():
     # Check if user is logged in
    if session.get("is_logged_in", False):
        files_list = utilities.get_files_list(SOURCE_BUCKET)
        return render_template("ContractHighlights.html",files_list=files_list)
    else:
        # If user is not logged in, redirect to login page
        return redirect(url_for('landing'))

    
@app.route('/')
def landing():
    return render_template("Landing.html")

# @app.route('/signup')
# def signup():
#     return render_template('SignUp.html')

# @app.route('/login')
# def login():
#     return render_template('Login.html')


# Route for user registration
@app.route("/register", methods=["POST", "GET"])
def register():
    if request.method == "POST":
        result = request.form
        email = result["email"]
        password = result["pass"]
        name = result["name"]
        if not authentication.check_password_strength(password):
            print("Password does not meet strength requirements")
            return redirect(url_for('landing'))
        try:
            # Create user account
            authentication.auth.create_user_with_email_and_password(email, password)
            # Authenticate user
            user = authentication.auth.sign_in_with_email_and_password(email, password)
            session["is_logged_in"] = True
            session["email"] = user["email"]
            session["uid"] = user["localId"]
            session["name"] = name
            # Save user data
            data = {"name": name, "email": email, "last_logged_in": datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}
            authentication.db.child("users").child(session["uid"]).set(data)
            return redirect(url_for('contracthighlight'))
        except Exception as e:
            print("Error occurred during registration: ", e)
            return redirect(url_for('landing'))
    else:
        # If user is logged in, redirect to welcome page
        if session.get("is_logged_in", False):
            return redirect(url_for('contracthighlight'))
        else:
            return redirect(url_for('landing'))

# Route for login result
@app.route("/loginresult", methods=["POST", "GET"])
def loginresult():
    if request.method == "POST":
        result = request.form
        email = result["email"]
        password = result["pass"]
        try:
            # Authenticate user
            user = authentication.auth.sign_in_with_email_and_password(email, password)
            session["is_logged_in"] = True
            session["email"] = user["email"]
            session["uid"] = user["localId"]
            # Fetch user data
            data = authentication.db.child("users").get().val()
            # Update session data
            if data and session["uid"] in data:
                session["name"] = data[session["uid"]]["name"]
                # Update last login time
                authentication.db.child("users").child(session["uid"]).update({"last_logged_in": datetime.now().strftime("%m/%d/%Y, %H:%M:%S")})
            else:
                session["name"] = "User"
            # Redirect to welcome page
            return redirect(url_for('contracthighlight'))
        except Exception as e:
            print("Error occurred: ", e)
            return redirect(url_for('landing'))
    else:
        # If user is logged in, redirect to welcome page
        if session.get("is_logged_in", False):
            return redirect(url_for('contracthighlight'))
        else:
            return redirect(url_for('landing'))

# Route for logout
@app.route("/logout")
def logout():
    # Update last logout time
    authentication.db.child("users").child(session["uid"]).update({"last_logged_out": datetime.now().strftime("%m/%d/%Y, %H:%M:%S")})
    session["is_logged_in"] = False
    return redirect(url_for('landing'))

def getfilecontent(file_paths):
    txt = ""
    for file in file_paths:
        path = Path(file)
        file_path_without_ext = str(path.parent / path.stem)
        txt += utilities.download_blob_as_string(DESTINATION_BUCKET,file_path_without_ext+".txt")
    return txt

@app.route("/getsummary",methods=["POST","GET"])
def getsummary():
    words = request.args.get("words")
    data = request.get_json()
    file_paths = data["file_paths"]
    contract_txt = getfilecontent(file_paths)
    prompt_parts = [
        "Provide brief summary of article in " +words+ " words. Don't include any suggestions. Don't include any clause names of contract.",contract_txt
    ]
    summary = gf.get_response(prompt_parts)
    return {"summary":summary}

@app.route("/getcontracthighlights",methods=["POST","GET"])
def getcontracthighlights():
    acv = request.args.get("acv")
    data = request.get_json()
    file_paths = data["file_paths"]
    contract_txt = getfilecontent(file_paths)
    print("fetching timeline")
    logger.log_text("fetching timeline")
    timeline_prompt_parts = [
        """Provide all timeline or duration information from below contract in form of json array with keys like Timestamp, EventType, EventDescription
  in descending order of Timestamp. Using provided details, give approximate date for each Event and add every possible detail regarding Event in EventDescription.
   Make sure to include all possible details""",contract_txt
    ]
    timeline = gf.get_response(timeline_prompt_parts)
    print("fetched timeline")
    logger.log_text("fetched timeline")
    time.sleep(10)
    print("fetching vendor company")
    logger.log_text("fetching vendor company")
    vendor_company_details_prompt_parts = [
            """Provide vendor details from below contract in form of json object with keys VendorName, VendorSignedBy, VendorRole.
            Use the definitions below for keys:
            VendorName : Who is the supplier of products
            VendorSignedBy : What is the name of the person who signed the agreement
            VendorRole : What the role or title or designation of person who signed the contract

            Provide company or reseller details from below contract in form of json object with keys CompanyName, CompanySignedBy, CompanyRole.
            Use the definitions below for keys:
            CompanyName : What is the company or reseller name that is utilizing services
            CompanySignedBy : What is the name of the person who signed the agreement
            CompanyRole : What the role or title or designation of person who signed the contract

            Provide Guarantor details from below contract in form of json object with keys GuarantorName, GuarantorSignedBy, GuarantorRole.
            Use the definitions below for keys:
            GuarantorName : What is the company name of Guarantor
            GuarantorSignedBy : What is the name of the person who signed the agreement as Guarantor
            GuarantorRole : What the role or title or designation of person who signed the contract as Guarantor

            Get Rebate amount and Discount Amount for Annual Contract Value of {acv} based on information provided in below contract in form of json with keys AnnualContractValue,Rebate,Discount.
            Include currency in all number representation.
            RebateAmount:Calculate Rebate Amount based on rebate table provided.Ignore rebate step-ups. Return response in $.
            Discount:Calculate Discount Amount based on discount table provided.Return response in $.
            
            return final result as json object with keys as Vendor,Company,Guarantor,Revenue and value as corresponding object. don't return that specific object if details are not found
            """.format(acv=acv),contract_txt
    ]
    vendor_company_details = gf.get_response(vendor_company_details_prompt_parts)
    print("fetched vendor company")
    logger.log_text("fetched vendor company")
    time.sleep(10)
    print("fetching rebates,products,outofscope")
    logger.log_text("fetching rebates,products,outofscope")
    tables_prompt_parts = [
            """
            Provide products and pricing details from below contract in form of json with columns ProductName, Price, Discount, Currency.
            For discount, get all the available discount options with conditions if any for each product as comma separated text.
            Don't include any clause names of contract.Return empty json array if no details are found.
            
            Add any additional notes related to Products and pricing as key ProductsNotes in the final json object in form of markdown list.Return "NONE" if no details are found.

            Provide Rebates details from below contract in form of json array with keys like AnnualContractValue, RebateStepUp(%), RebateStepUp, CumulativeRebate,
            AnnualisedTotalPostRebate, RebateOverall(%).Don't include any clause names of contract.Include currency wherever applicable for numbers in json.
            Return empty json array if no details are found.

            Add any additional notes related to Rebates as key RebatesNotes in the final json object in form of markdown list.Return "NONE" if no details are found.

            Get details about Out of Scope Work charges like professional and managed services in form of json with columns Level, Role, StandardDailyRate, Discount.
            For discount, get all the available discount options with conditions as comma separated text if any.
            Include currency wherever applicable.Don't include any clause names of contract.Return empty json array if no details are found.
            
            Add any additional notes of out of scope work or professional services related as key OutOfScopeNotes in the final json object in form of markdown list.Return "NONE" if no details are found.

            return final result as json object with keys as Products,ProductsNotes,Rebates,RebatesNotes,OutOfScope,OutOfScopeNotes and value as corresponding object.
            """,contract_txt
    ]
    tables = gf.get_response(tables_prompt_parts)
    print("fetched rebates,products,outofscope")
    logger.log_text("fetched rebates,products,outofscope")
    time.sleep(10)
    print("fetching allhighlights")
    logger.log_text("fetching allhighlights")
    allhighlights_prompt_parts = [
        """Get all terms or conditions related to Amendments, Exclusivity or Minimum Volumes, Payment or Payment Disputes, Invoicing, Interest of late payment,
            Supply chain facility from below contract in form of json with each section as key and value as nested bullet string.
            Dont provide any additional suggestions.Return value as "NONE" if no details are found about that particular section. Don't return that specific section if details are not found or value is "NONE".""",contract_txt
    ]
    allhighlights = gf.get_response(allhighlights_prompt_parts)
    print("fetched allhighlights")
    logger.log_text("fetched allhighlights")
    # time.sleep(10)
    # print("fetching payment terms")
    # payment_prompt_parts = [
    #     """Get all Payment or invoicing terms if any from below contract in form of nested bullet list.Return 'NONE' if no details are found""",contract_txt
    # ]
    # payment = gf.get_response(payment_prompt_parts)
    # print("fetched payment terms")
    return {"timeline":timeline,"vendor_company":vendor_company_details,"tables":tables,"allhighlights":allhighlights}

@app.route("/ocrextract",methods=["POST","GET"])
def ocrextract():
    data = request.get_json()
    file_path_old = data["file_paths"][0]
    path_old = Path(file_path_old)
    file_path = str(path_old.parent / path_old.stem )+"/"+path_old.name
    #file_paths = utilities.get_file_paths(SOURCE_BUCKET)
    #for file_path in file_paths:
    path = Path(file_path)
    file_path_without_ext = str(path.parent / path.stem)
    # if utilities.check_file_exists("supplychain-datastore-extracted",file_path_without_ext+".txt") == False:
    source_uri = f"gs://{SOURCE_BUCKET}/{file_path}"
    destination_uri = f"gs://{OCR_BUCKET}/{file_path_without_ext}"
    utilities.detect_document(source_uri,destination_uri)
    utilities.write_extracted_text(destination_uri)
    utilities.upload_blob(DESTINATION_BUCKET,"static/temp/ocr_extracted.txt",file_path_without_ext+".txt")
    Path("static/temp/ocr_extracted.txt").unlink()
    return "True"

@app.route("/createragdb",methods=["POST","GET"])
def createragdb():
    global rag_db
    data = request.get_json();
    file_paths = data["file_paths"]
    contract_txt = getfilecontent(file_paths)
    dir_path = "static/temp/RAG"
    #path = Path(dir_path)
    #shutil.rmtree(path,ignore_errors=True)
    chunked_text = utilities.split_text(contract_txt)
    print("started rag creation")
    logger.log_text("started rag creation")
    rag_db,name =gf.create_chroma_db(documents=chunked_text,
                          path=dir_path,
                          name="ezycontract_rag")
    print("created rag")
    logger.log_text("created rag")
    #rag_db=gf.load_chroma_collection(path="static/temp/RAG", name="ezycontract_rag")
    return "True"

@app.route("/getpromptresponse")
def getpromptresponse():
    user_prompt = request.args.get("user_prompt")
    answer = gf.generate_answer(rag_db,query=user_prompt)
    return answer

@app.route("/uploadfiles",methods=["POST"])
def uploadfiles():
    file = request.files["UploadFiles"]
    print(file)
    filePath = request.args.get("selectedPath")
    #for file in files:
        # filename = file.filename
    path = Path(file.filename)
    file_path_without_ext = str(path.parent / path.stem)
    utilities.upload_blob_obj(SOURCE_BUCKET,file,filePath+file_path_without_ext+"/"+file.filename)
    return "True"

# @app.route('/ContractHighlightsOld')
# def ContractHighlightsOld():
#     text = utilities.download_blob_as_string("supplychain-datastore-extracted","Amy_Cripto_EncounterDetails.txt")
#     prompt_parts = [
#         "Provide brief summary of article in 200 words",text
#     ]
#     summary = gf.get_response(prompt_parts)
#     return render_template('templates/ContractHighlights.html', Summary=summary)

if __name__ == '__main__':
    # createragdb()
    server_port = os.environ.get('PORT', '8080')
    app.run(debug=True, port=server_port, host='0.0.0.0')
