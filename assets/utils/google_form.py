import os
import json
import traceback
import argparse
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from googleapiclient.discovery import Resource
from apiclient import discovery

form_template = {
    "info": {
        "title": "諮商回饋單",
    }
}

form_auth_scopes = ["https://www.googleapis.com/auth/forms.body"]
form_ans_scopes = ["https://www.googleapis.com/auth/forms.responses.readonly"]
discovery_doc = "https://forms.googleapis.com/$discovery/rest?version=v1"


def get_form_object(token_path, scopes, client_secrets_path: str = "./assets/credentials/client_secret.json") -> Resource:
    credentials = None
    if os.path.exists(token_path):
        credentials = Credentials.from_authorized_user_file(
            token_path, scopes)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_path, scopes)
            credentials = flow.run_local_server(port=8899)
        with open(token_path, "w") as token:
            token.write(credentials.to_json())
    try:
        form_service = discovery.build(
            'forms', 'v1', credentials=credentials, discoveryServiceUrl=discovery_doc, static_discovery=False)
        return form_service
    except HttpError as error:
        traceback.print_exc()
        return None


def format_qa_pairs(response_json_path: str) -> str:
    data = json.load(
        open(response_json_path, 'r', encoding='utf-8'))
    questions = data.get('questions', [])
    answers = data.get('answers', [])
    report_markdown = data.get('report_markdown', [])
    combined = ""
    max_len = max(len(questions), len(answers))
    for i in range(max_len):
        if i < len(questions):
            combined += f"AI : {questions[i]}\n"
        if i < len(answers):
            combined += f"回答 : {answers[i]}\n"
            combined += "-  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -\n"

    combined += "\n"+report_markdown
    return combined


def find_question_title(questionnaire_template, question_id):
    requests = questionnaire_template.get('requests', [])

    for request in requests:
        create_item = request.get('createItem', {})
        item = create_item.get('item', {})

        if 'questionItem' not in item:
            continue

        question_item = item['questionItem']

        if 'question' not in question_item:
            continue

        question = question_item['question']

        if 'questionId' in question and question['questionId'] == question_id:
            return item['title']

    return None


def format_answers(result, questionnaire_template_path: str = "./assets/database/questionnaire_template.json", question_ids_path: str = "./assets/database/question_ids.json"):
    questionnaire_template = json.load(
        open(questionnaire_template_path, 'r', encoding='utf-8'))
    question_ids = json.load(
        open(question_ids_path, 'r', encoding='utf-8'))

    questions = []
    answers = []

    for id in question_ids:
        question = find_question_title(questionnaire_template, id)
        if question is not None:
            questions.append(question)
            data = result['responses'][-1]['answers'].get(id, None)
            ans = "" if data == None else data['textAnswers']['answers'][-1]['value']
            answers.append(ans)

    return questions, answers


def create_form(
    discord_id,
    database_folder_path: str = "./assets/database/psygpt_database/",
    form_auth_token_path: str = "./assets/credentials/form_auth_token.json",
    questionnaire_template_path: str = "./assets/database/questionnaire_template.json",
    client_secrets_path: str = "./assets/credentials/client_secret.json",
):
    user_response_json_path = os.path.join(
        database_folder_path, discord_id+".json")

    # Check if user has already created a form
    user_response_json_data = json.load(
        open(user_response_json_path, 'r', encoding='utf-8'))
    if 'form_id' in user_response_json_data:
        print(
            f"User {discord_id} has already created a form, form id is {user_response_json_data['form_id']}\nPlease go to {user_response_json_data['form_url']} to submit the questionnaire.")
        return user_response_json_data['form_id'], user_response_json_data['form_url']

    form_object = get_form_object(
        form_auth_token_path, form_auth_scopes, client_secrets_path=client_secrets_path)
    form = form_object.forms().create(body=form_template).execute()

    questionnaire_template_data = json.load(
        open(questionnaire_template_path, 'r', encoding='utf-8'))
    questionnaire_template_data['requests'][-1]['createItem']['item']['description'] = format_qa_pairs(
        user_response_json_path)
    form_object.forms().batchUpdate(
        formId=form["formId"], body=questionnaire_template_data).execute()
    return form["formId"], f"https://docs.google.com/forms/d/{form['formId']}/viewform"


def get_form(
    form_id,
    form_ans_token_path: str = "./assets/credentials/form_ans_token.json",
    questionnaire_template_path: str = "./assets/database/questionnaire_template.json",
    question_ids_path: str = "./assets/database/question_ids.json",
    client_secrets_path: str = "./assets/credentials/client_secret.json",
):
    form_object = get_form_object(form_ans_token_path, form_ans_scopes,
                                  client_secrets_path=client_secrets_path)
    result = form_object.forms().responses().list(formId=form_id).execute()

    if 'responses' not in result:
        print("Questionnaire has no response yet, please try again once a user completed.")
        return None, None

    questions, answers = format_answers(
        result, questionnaire_template_path, question_ids_path)

    return questions, answers


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, required=True)
    parser.add_argument("--mode", type=str, required=True)
    parser.add_argument("--inplace", action="store_true", default=True)
    parser.add_argument("--database_folder_path", type=str,
                        default="./assets/database/psygpt_database/")
    parser.add_argument("--form_auth_token_path", type=str,
                        default="./assets/credentials/form_auth_token.json")
    parser.add_argument("--form_ans_token_path", type=str,
                        default="./assets/credentials/form_ans_token.json")
    parser.add_argument("--client_secrets_path", type=str,
                        default="./assets/credentials/client_secret.json")
    parser.add_argument("--questionnaire_template_path", type=str,
                        default="./assets/database/questionnaire_template.json")
    parser.add_argument("--question_ids_path", type=str,
                        default="./assets/database/question_ids.json")

    args = parser.parse_args()

    if args.mode == "create_form":
        form_id, url = create_form(args.id,
                                   database_folder_path=args.database_folder_path,
                                   form_auth_token_path=args.form_auth_token_path,
                                   questionnaire_template_path=args.questionnaire_template_path,
                                   client_secrets_path=args.client_secrets_path
                                   )
        print(f"\tYour form id is {form_id}\n\tYour form url is {url}")

        if args.inplace:
            user_response_json_path = os.path.join(
                args.database_folder_path, args.id+".json")
            user_response_json_data = json.load(
                open(user_response_json_path, 'r', encoding='utf-8'))
            user_response_json_data['form_id'] = form_id
            user_response_json_data['form_url'] = url
            with open(user_response_json_path, 'w', encoding='utf-8') as f:
                json.dump(user_response_json_data, f,
                          ensure_ascii=False, indent=4)

    elif args.mode == "get_form":
        user_response_json_path = os.path.join(
            args.database_folder_path, args.id+".json")
        user_response_json_data = json.load(
            open(user_response_json_path, 'r', encoding='utf-8'))
        questions, answers = get_form(user_response_json_data['form_id'],
                                      form_ans_token_path=args.form_ans_token_path,
                                      questionnaire_template_path=args.questionnaire_template_path,
                                      question_ids_path=args.question_ids_path,
                                      client_secrets_path=args.client_secrets_path,
                                      )
        print(f"Questions: \n\n{questions}\n\nAnswers: \n\n{answers}\n")

        if args.inplace:
            user_response_json_data['form_questions'] = questions
            user_response_json_data['form_answers'] = answers
            with open(user_response_json_path, 'w', encoding='utf-8') as f:
                json.dump(user_response_json_data, f,
                          ensure_ascii=False, indent=4)
    else:
        print("Invalid mode name, choose from 'create_form' or 'get_form'.")
