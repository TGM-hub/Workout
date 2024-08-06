import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.dependencies import Input, Output, State
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import os
import requests
import base64
import json

# Load the CSV files
df = pd.read_csv('split.csv')
df_log = pd.read_csv('exercise_log_csv.csv')

# Transform the DataFrame to a long format
df_long = df.melt(var_name='Workout', value_name='Exercise').dropna()

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server  # Expose the Flask server instance for gunicorn

# Define the layout of the app
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.Label('Select Workout', style={'font-size': '18px', 'margin-top': '10px'}),
            dcc.Dropdown(
                id='workout-dropdown',
                options=[{'label': workout, 'value': workout} for workout in df.columns],
                value=None,
                style={'font-size': '16px'}
            ),
        ], width=12),
    ], className='mb-3'),
    dbc.Row([
        dbc.Col([
            html.Label('Select Exercise', style={'font-size': '18px', 'margin-top': '10px'}),
            dcc.Dropdown(
                id='exercise-dropdown',
                options=[],
                value=None,
                style={'font-size': '16px'}
            ),
        ], width=12),
    ], className='mb-3'),
    dbc.Row([
        dbc.Col([
            html.Label('Reps', style={'font-size': '18px', 'margin-top': '10px'}),
            dbc.Input(id='reps-input', type='number', min=0, step=1, style={'font-size': '16px'}),
        ], width=6, className='mb-3'),
        dbc.Col([
            html.Label('Weight', style={'font-size': '18px', 'margin-top': '10px'}),
            dbc.Input(id='weight-input', type='number', min=0, step=1, style={'font-size': '16px'}),
        ], width=6, className='mb-3'),
    ]),
    dbc.Row([
        dbc.Col([
            html.Label('Form', style={'font-size': '18px', 'margin-top': '10px'}),
            dbc.Input(id='form-input', type='number', min=0, max=10, step=1, style={'font-size': '16px'}),
        ], width=6, className='mb-3'),
        dbc.Col([
            html.Label('RIR', style={'font-size': '18px', 'margin-top': '10px'}),
            dbc.Input(id='rir-input', type='number', min=0, max=3, step=1, style={'font-size': '16px'}),
        ], width=6, className='mb-3'),
    ]),
    dbc.Row([
        dbc.Col([
            html.Label('Comments', style={'font-size': '18px', 'margin-top': '10px'}),
            dbc.Input(id='comments-input', type='text', style={'font-size': '16px'}),
        ], width=12, className='mb-3'),
    ]),
    dbc.Row([
        dbc.Col([
            dbc.Button('Save', id='save-button', color='primary', className='mt-2', style={'width': '100%', 'font-size': '18px'}),
            html.Div(id='save-status', className='mt-2', style={'font-size': '16px'})
        ], width=12),
    ], className='mb-3'),
    dbc.Row([
        dbc.Col([
            html.H3('Exercise History', style={'font-size': '20px', 'margin-top': '20px'}),
            html.Div(id='exercise-history')
        ], width=12),
    ], className='mb-3'),
    dbc.Row([
        dbc.Col([
            html.H3('5Max Over Time', style={'font-size': '20px', 'margin-top': '20px'}),
            dcc.Graph(id='5max-chart')
        ], width=12),
    ], className='mb-3'),
], fluid=True)

# Callback to update the exercise dropdown based on the selected workout
@app.callback(
    Output('exercise-dropdown', 'options'),
    [Input('workout-dropdown', 'value')]
)
def update_exercise_dropdown(selected_workout):
    if selected_workout is None:
        return []
    exercises = df_long[df_long['Workout'] == selected_workout]['Exercise'].unique()
    return [{'label': exercise, 'value': exercise} for exercise in exercises]

# Function to calculate 5Max
def calculate_5max(reps, weight, rir):
    try:
        reps = int(reps)
        rir = int(rir)
        weight = float(weight)
        multipliers = {
            3: 0.935, 4: 0.963, 5: 1, 6: 1.02,
            7: 1.048, 8: 1.077, 9: 1.105, 10: 1.133,
            11: 1.162, 12: 1.19
        }
        total_reps = reps + rir
        multiplier = multipliers.get(total_reps)
        if multiplier is not None:
            return weight * multiplier
        else:
            return None
    except (ValueError, TypeError) as e:
        print(f"Error: {e}")
        return None

# Function to push changes to GitHub
def push_to_github(file_path, repo, branch, token):
    with open(file_path, 'r') as file:
        content = file.read()
    content_encoded = base64.b64encode(content.encode()).decode()
    url = f'https://api.github.com/repos/{repo}/contents/{file_path}'
    headers = {
        'Authorization': f'token {token}',
        'Content-Type': 'application/json'
    }
    # Get the SHA of the existing file
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        sha = response.json()['sha']
    else:
        sha = None
    data = {
        'message': 'Update exercise log',
        'content': content_encoded,
        'branch': branch
    }
    if sha:
        data['sha'] = sha
    response = requests.put(url, headers=headers, data=json.dumps(data))
    if response.status_code == 201 or response.status_code == 200:
        print('File updated successfully on GitHub.')
    else:
        print(f'Failed to update file on GitHub: {response.json()}')

@app.callback(
    [Output('save-status', 'children'),
     Output('exercise-history', 'children'),
     Output('5max-chart', 'figure')],
    [Input('save-button', 'n_clicks')],
    [State('workout-dropdown', 'value'),
     State('exercise-dropdown', 'value'),
     State('reps-input', 'value'),
     State('weight-input', 'value'),
     State('form-input', 'value'),
     State('comments-input', 'value'),
     State('rir-input', 'value')]
)
def save_and_update(n_clicks, workout, exercise, reps, weight, form, comments, rir):
    global df_log
    if n_clicks is None:
        return '', '', {}
    # Check if any required field is None or empty
    if None in [workout, exercise, reps, weight, form, rir] or '' in [str(reps), str(weight), str(form), str(rir)]:
        return 'Please fill in all fields.', '', {}
    # Debugging statements
    print(f"Workout: {workout}, Exercise: {exercise}, Reps: {reps}, Weight: {weight}, Form: {form}, RIR: {rir}, Comments: {comments}")
    # Validate numeric inputs
    try:
        reps = int(reps)
        weight = float(weight)
        form = int(form)
        rir = int(rir)
    except ValueError as e:
        return f'Invalid input: {e}', '', {}
    # Calculate 5Max
    max5 = calculate_5max(reps, weight, rir)
    if max5 is None:
        return 'Invalid inputs for 5Max calculation.', '', {}
    # Ensure comments is a string
    comments = comments or ""
    try:
        # Check if the last save for the same workout and exercise was within 2 minutes
        last_entry = df_log[(df_log['Workout'] == workout) & (df_log['Exercise'] == exercise)].tail(1)
        if not last_entry.empty:
            last_time = datetime.strptime(last_entry['Time'].values[0], '%Y-%m-%d %H:%M:%S')
            if datetime.now() - last_time < timedelta(minutes=2):
                return 'You can only save once every 2 minutes.', '', {}
        # Append the new entry to the DataFrame
        new_entry = pd.DataFrame([{
            'Time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Workout': workout,
            'Exercise': exercise,
            'Reps': reps,
            'Weight': weight,
            'RIR': rir,
            'Form': form,
            'Max5': max5,
            'Comments': comments
        }])
        df_log = pd.concat([df_log, new_entry], ignore_index=True)
        # Save the updated DataFrame to the CSV file
        exercise_log_csv = 'exercise_log_csv.csv'
        df_log.to_csv(exercise_log_csv, index=False)
        # Push changes to GitHub
        repo = 'TGM-hub/Workout'
        branch = 'main'
        token = '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'
        push_to_github(exercise_log_csv, repo, branch, token)
    except Exception as e:
        return f'An error occurred: {str(e)}', '', {}
    # Update exercise history
    exercise_history = df_log[df_log['Exercise'] == exercise].sort_values(by='Time', ascending=False).head(5)
    if exercise_history.empty:
        history_content = 'No history available for this exercise.'
    else:
        best_set = exercise_history.sort_values(by=['RIR', 'Form', 'Max5'], ascending=[True, False, False]).head(1)
        table_header = [
            html.Thead(html.Tr([html.Th(col) for col in ['Time', 'Workout', 'Reps', 'Weight', 'RIR', 'Form', 'Max5']]))
        ]
        table_body = [html.Tbody([
            html.Tr([html.Td(cell) for cell in row], style={'backgroundColor': '#d4edda'} if row.equals(best_set.iloc[0]) else {})
            for _, row in exercise_history.iterrows()
        ])]
        history_content = dbc.Table(table_header + table_body, bordered=True, striped=True, hover=True)
    # Update 5Max chart
    exercise_data = df_log[df_log['Exercise'] == exercise].sort_values(by='Time')
    if exercise_data.empty:
        chart_content = {}
    else:
        chart_content = px.line(exercise_data, x='Time', y='Max5', title=f'5Max Over Time for {exercise}')
    return 'Data saved successfully.', history_content, chart_content

# Run the app
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 80))
    app.run_server(debug=False, host='0.0.0.0', port=port)
