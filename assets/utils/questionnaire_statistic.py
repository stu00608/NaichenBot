import os
import json
import random
import datetime
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import seaborn as sns
import numpy as np
from assets.utils.google_form import get_form

font_path = "./assets/TaipeiSansTCBeta-Regular.ttf"


def generate_data(amount):
    data = ['沒有', '2', '2', '2', '2', '2', '2', '2',
            '2', '2', '2', '2', '2', 'a', 'a', 'a', 'a']
    generated_data = []

    for _ in range(amount):
        generated_data.append([
            random.choice(['有', '沒有']),
            *[str(random.randint(1, 5)) for _ in range(12)],
            *data[-4:]
        ])

    return generated_data


def create_dataframe(data, column_names=None):
    converted_data = []

    for d in data:
        converted_data.append([
            5 if d[0] == '有' else 1,
            *[int(num) for num in d[1:13]],
        ])

    columns = [
        '有/沒有'] + [f'Element{i}' for i in range(1, 13)] if column_names == None else column_names
    df = pd.DataFrame(converted_data, columns=columns)

    return df


def plot_column(df, column, output_file_path: str = "plot.png"):
    print(output_file_path)
    plt.figure(figsize=(8, 6))
    sns.set_style("whitegrid", {'axes.grid': False})

    if isinstance(column, int):
        column_data = df.iloc[:, column]
    elif isinstance(column, str):
        column_data = df[column]
    else:
        raise TypeError("column must be either int or str")

    font = FontProperties(
        fname=font_path, size=14)

    hist, bins = np.histogram(column_data, bins=np.arange(1, 7))
    print(hist)
    max_value = hist.max()

    colors = ['red' if hist[i] ==
              max_value else 'blue' for i in range(len(hist))]
    plt.cla()
    bars = plt.bar(bins[:-1], hist, width=(bins[1]-bins[0]),
                   color=colors, alpha=0.7)
    plt.title(column, fontproperties=font, fontsize=14)
    plt.xlabel('分數', fontproperties=font, fontsize=12)
    plt.ylabel('人數', fontproperties=font, fontsize=12)
    plt.xticks(np.arange(1, 6))
    plt.yticks(np.arange(1, 25, 2))
    # Add value tags on top of each bar
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2, height, str(int(height)),
                 ha='center', va='bottom', fontproperties=font)
    # Add text at left bottom corner
    plt.text(0, -2.5, '非常不同意',
             fontproperties=font, fontsize=12)
    # Add text at right bottom corner
    plt.text(6, -2.5, '非常同意',
             fontproperties=font, fontsize=12, ha='right')

    plt.savefig(output_file_path)


def analyze_data(data, column_names, output_folder_path="./assets/database/psygpt_statistics/"):
    df = create_dataframe(data, column_names)
    print(df.head())

    os.makedirs(output_folder_path, exist_ok=True)

    print(column_names)

    for name in column_names:
        output_file_path = os.path.join(output_folder_path, name+".png")
        plot_column(df, name, output_file_path=output_file_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--overwrite", action="store_true", default=False)
    parser.add_argument("--debug", action="store_true", default=False)
    parser.add_argument("--database_folder_path", type=str,
                        default="./assets/database/psygpt_database/")
    parser.add_argument("--form_ans_token_path", type=str,
                        default="./assets/credentials/form_ans_token.json")
    parser.add_argument("--client_secrets_path", type=str,
                        default="./assets/credentials/client_secret.json")
    parser.add_argument("--questionnaire_template_path", type=str,
                        default="./assets/database/questionnaire_template.json")
    parser.add_argument("--question_ids_path", type=str,
                        default="./assets/database/question_ids.json")
    parser.add_argument("--statistics_folder_path", type=str,
                        default="./assets/database/psygpt_statistics/")
    args = parser.parse_args()

    if args.debug:
        data = generate_data(50)
        # print(json.dumps(data, indent=4))
        analyze_data(data, [str(i) for i in range(13)])
        exit(0)

    # Loop through all .json files that not start with "old_" in args.database_folder_path, store the abs path into a list
    user_response_json_paths = [os.path.join(args.database_folder_path, file_name) for file_name in os.listdir(
        args.database_folder_path) if file_name.endswith(".json") and not file_name.startswith("old_")]

    global_questions = None
    global_answers = []

    for user_response_json_path in user_response_json_paths:
        user_id = os.path.basename(user_response_json_path).split(".")[0]
        print(f"Processing {user_id}...")

        # Check if `form_questions` and `form_answers` are already in the json file
        user_response_json_data = json.load(
            open(user_response_json_path, 'r', encoding='utf-8'))

        # Get questions and answers from Google Form or from the json file
        if 'form_questions' in user_response_json_data and \
            'form_answers' in user_response_json_data and \
            'form_questions_ids' in user_response_json_data and \
                not args.overwrite:
            questions = user_response_json_data['form_questions']
            answers = user_response_json_data['form_answers']
            questions_ids = user_response_json_data['form_questions_ids']

            if global_questions == None:
                global_questions = questions
            elif global_questions != questions:
                print("Found different version of questions")
                continue

            # Check if questions_ids is equal to the one in args.question_ids_path json data
            if questions_ids != json.load(open(args.question_ids_path, 'r', encoding='utf-8')):
                print("Found different version of questions_ids")
                continue
        else:
            questions, answers = get_form(user_id,
                                          form_ans_token_path=args.form_ans_token_path,
                                          client_secrets_path=args.client_secrets_path,
                                          questionnaire_template_path=args.questionnaire_template_path,
                                          question_ids_path=args.question_ids_path)
            if questions == None or answers == None:
                continue
            questions_ids = json.load(
                open(args.question_ids_path, 'r', encoding='utf-8'))

        global_answers.append(answers)

    today = datetime.datetime.now().strftime("%Y%m%d")
    output_folder_path = os.path.join(args.statistics_folder_path, today)
    analyze_data(global_answers, global_questions[:13],
                 output_folder_path=output_folder_path)
