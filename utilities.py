from pypdf import PdfReader
from google.cloud import storage
from google.cloud import vision
import re
import json
import os
from dotenv import load_dotenv
load_dotenv()

PROJECT_ID = os.environ.get("PROJECT_ID")
storage_client = storage.Client(project=PROJECT_ID)
    
def detect_document(source_uri,destination_uri):
    mime_type = "application/pdf"
    batch_size = 100
    vision_client = vision.ImageAnnotatorClient()
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

    gcs_source = vision.GcsSource(uri = source_uri)
    input_config = vision.InputConfig(gcs_source = gcs_source,mime_type=mime_type)

    gcs_destination = vision.GcsDestination(uri = destination_uri)
    output_config = vision.OutputConfig(gcs_destination = gcs_destination,batch_size=batch_size)

    async_request = vision.AsyncAnnotateFileRequest(features=[feature],input_config=input_config,output_config=output_config)

    operation = vision_client.async_batch_annotate_files(requests=[async_request])
    print("waiting for operation to finish")
    operation.result(timeout=420)

def write_extracted_text(destination_uri):
    match_str = re.match(r'gs://([^/]+)/(.+)',destination_uri)
    bucket_name = match_str.group(1)
    prefix = match_str.group(2)

    bucket = storage_client.get_bucket(bucket_name)
    blob_list = list(bucket.list_blobs(prefix=prefix))
    print('Output files:')
    for blob in blob_list:
      print(blob.name)

    for n in range(len(blob_list)):
      output = blob_list[n]
      json_string = output.download_as_string()
      response = json.loads(json_string)
      file = open("static/temp/ocr_extracted.txt".format(str(n)),"a")
      for m in range(len(response["responses"])):
        first_page_response = response['responses'][m]
        annotation = first_page_response["fullTextAnnotation"]
        file.write(annotation['text'] + "\n\n\n")

def upload_blob(bucket_name, source_file_name, destination_blob_name):
  """Uploads a file from local to the bucket."""

  bucket = storage_client.get_bucket(bucket_name)
  blob = bucket.blob(destination_blob_name)
  with open(source_file_name, 'rb') as source_file:
    blob.upload_from_file(source_file)

def upload_blob_obj(bucket_name, source_file, destination_blob_name):
  """Uploads a file object to the bucket."""

  bucket = storage_client.get_bucket(bucket_name)
  blob = bucket.blob(destination_blob_name)
  blob.upload_from_file(source_file)

def download_blob_as_string(bucket_name, blob_name):
  bucket = storage_client.get_bucket(bucket_name)
  blob = bucket.get_blob(blob_name)
  blob_content = blob.download_as_text(encoding="utf-8")
  return blob_content

def get_file_paths(bucket_name):
    blobs = storage_client.list_blobs(bucket_name)
    blob_list = []
    for blob in blobs:
        if not blob.name.endswith("/"):
            blob_list.append(blob.name)
    blob_list.sort(key=len)
    return blob_list

def get_files_list(bucket_name):
    blobs = storage_client.list_blobs(bucket_name)
    blob_list = []
    for blob in blobs:
        if not blob.name.endswith("/"):
            blob_list.append(blob.name)
    blob_list.sort(key=len)
    file_hierarchy = group_files(blob_list)    
    return file_hierarchy

def load_pdf(file_path):
    """
    Reads the text content from a PDF file and returns it as a single string.

    Parameters:

    - file_path (str): The file path to the PDF file.

    Returns:
    - str: The concatenated text content of all pages in the PDF.
    """
    # Logic to read pdf
    reader = PdfReader(file_path)

    # Loop over each page and store it in a variable
    text = ""
    for page in reader.pages:
        text += page.extract_text()

    return text

def split_text(text: str):
    """
    Splits a text string into a list of non-empty substrings based on the specified pattern.
    The "\n\n\n" pattern will split the document para by para
    Parameters:
    - text (str): The input text to be split.

    Returns:
    - List[str]: A list containing non-empty substrings obtained by splitting the input text.

    """
    split_text = re.split('\n\n\n', text)
    return [i for i in split_text if i != ""]

def check_password_strength(password):
    # At least one lower case letter, one upper case letter, one digit, one special character, and at least 8 characters long
    return re.match(r'^(?=.*\d)(?=.*[!@#$%^&*])(?=.*[a-z])(?=.*[A-Z]).{8,}$', password) is not None

import os

def group_files(files_list):
    result = []
    for file_path in files_list:
        # Extract directory path without the filename
        folder_path = os.path.dirname(file_path)
        folder_list = folder_path.split("/",1)
        # If the folder is the root, parent ID is None
        if len(folder_list) == 1:
            parent_id = None
        else:
            #Get the parent id by searching the result list
            req_obj = [item for item in result if item['path'].rsplit("/",1)[0] == folder_path.rsplit("/",1)[0]][0]
            parent_id = req_obj["id"]
            
        # Add file data to result
        file_data = {
            'id': str(len(result) + 1),  # Unique ID for each file
            'name': os.path.basename(file_path),
            'path': file_path,
            'parentId': parent_id,
            'hasChild': False
        }  
        result.append(file_data)

        #Check if children exists based on parent_id
        for file in result:
          childExists = [item for item in result if item['parentId'] == file["id"]]
          if len(childExists) > 0:
            file["hasChild"] = True
    return result

def check_file_exists(bucket_name, file_name):
    """
    Check if a file exists in Google Cloud Storage.
    
    Args:
        bucket_name (str): Name of the GCS bucket.
        file_name (str): Name of the file to check.
    
    Returns:
        bool: True if the file exists, False otherwise.
    """
    # Get the bucket
    bucket = storage_client.bucket(bucket_name)

    # Check if the file exists
    print(file_name)
    blob = bucket.blob(file_name)
    return blob.exists()