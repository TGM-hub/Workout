import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.dependencies import Input, Output, State
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import os

# Load the CSV file
df = pd.read_csv('split.csv')

# Transform the DataFrame to a long format
df_long = df.melt(var_name='Workout', value_name='Exercise').dropna()

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server  # Expose the Flask server instance for gunicorn

def init_db():
    conn = sqlite3.connect('exercise_log.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exercise_log (
            id INTEGER PRIMARY KEY,
            Time TEXT,
            Workout TEXT,
            Exercise TEXT,
            Reps INTEGER,
            Weight INTEGER,
            RIR INTEGER,
            Form INTEGER,
            Max5 REAL,
            Comments TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Call the database initialization function
init_db()

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
            dbc.Input(id='rir-input', type='number', min=0, max=10, step=1, style={'font-size': '16px'}),
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
        # Convert inputs to integers
        reps = int(reps)
        rir = int(rir)
        
        # Define a dictionary for multipliers
        multipliers = {
            3: 0.935,
            4: 0.963,
            5: 1,
            6: 1.02,
            7: 1.048,
            8: 1.077,
            9: 1.105,
            10: 1.133,
            11: 1.162,
            12: 1.19
        }
        
        # Calculate total reps
        total_reps = reps + rir
        
        # Lookup multiplier based on total reps
        multiplier = multipliers.get(total_reps)
        
        # Calculate and return 5Max, or return None if total_reps is not in multipliers
        if multiplier is not None:
            return weight * multiplier
        else:
            return None
    except (ValueError, TypeError):
        # Handle the case where conversion fails or inputs are invalid
        print("Invalid input for reps or rir; must be integers.")
        return None

# Callback to save the data to the SQLite database
@app.callback(
    Output('save-status', 'children'),
    [Input('save-button', 'n_clicks')],
    [State('workout-dropdown', 'value'),
     State('exercise-dropdown', 'value'),
     State('reps-input', 'value'),
     State('weight-input', 'value'),
     State('form-input', 'value'),
     State('comments-input', 'value'),
     State('rir-input', 'value')]
)
def save_to_db(n_clicks, workout, exercise, reps, weight, form, rir, comments):
    if n_clicks is None:
        return ''
    if None in [workout, exercise, reps, weight, form, rir]:
        return 'Please fill in all fields.'
    # Calculate 5Max
    max5 = calculate_5max(reps, weight, rir)
    try:
        # Connect to SQLite database
        conn = sqlite3.connect('exercise_log.db')
        cursor = conn.cursor()
        
        # Check if the last save for the same workout and exercise was within 2 minutes
        cursor.execute('''
            SELECT Time
            FROM exercise_log
            WHERE Workout = ? AND Exercise = ?
            ORDER BY Time DESC
            LIMIT 1
        ''', (workout, exercise))
        last_time = cursor.fetchone()
        
        if last_time:
            last_time = datetime.strptime(last_time[0], '%Y-%m-%d %H:%M:%S')
            if datetime.now() - last_time < timedelta(minutes=2):
                return 'You can only save once every 2 minutes.'
        
        # Insert data into the table
        cursor.execute('''
            INSERT INTO exercise_log (Time, Workout, Exercise, Reps, Weight, RIR, Form, Max5, Comments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), workout, exercise, reps, weight, rir, form, max5, comments))
        
        # Commit the changes and close the connection
        conn.commit()
        conn.close()
    except Exception as e:
        return f'An error occurred: {str(e)}'
    
    return 'Data saved successfully.'

# Callback to display the exercise history
@app.callback(
    Output('exercise-history', 'children'),
    [Input('exercise-dropdown', 'value')]
)
def display_exercise_history(selected_exercise):
    if selected_exercise is None:
        return ''
    # Connect to SQLite database
    conn = sqlite3.connect('exercise_log.db')
    cursor = conn.cursor()
    # Query the database for the selected exercise
    cursor.execute('''
        SELECT Time, Workout, Reps, Weight, RIR, Form, Max5
        FROM exercise_log
        WHERE Exercise = ?
        ORDER BY Time DESC
        LIMIT 5
    ''', (selected_exercise,))
    rows = cursor.fetchall()
    # Query for the best set
    cursor.execute('''
        SELECT Time, Workout, Reps, Weight, RIR, Form, Max5
        FROM exercise_log
        WHERE Exercise = ?
        ORDER BY RIR ASC, Form DESC, Max5 DESC
        LIMIT 1
    ''', (selected_exercise,))
    best_set = cursor.fetchone()
    conn.close()
    if not rows:
        return 'No history available for this exercise.'
    # Create a table to display the history
    table_header = [
        html.Thead(html.Tr([html.Th(col) for col in ['Time', 'Workout', 'Reps', 'Weight', 'RIR', 'Form', 'Max5']]))
    ]
    table_body = [html.Tbody([
        html.Tr([html.Td(cell) for cell in row], style={'backgroundColor': '#d4edda'} if row == best_set else {})
        for row in rows
    ])]
    return dbc.Table(table_header + table_body, bordered=True, striped=True, hover=True)

# Callback to display the 5Max over time chart
@app.callback(
    Output('5max-chart', 'figure'),
    [Input('exercise-dropdown', 'value')]
)
def update_5max_chart(selected_exercise):
    if selected_exercise is None:
        return {}
    # Connect to SQLite database
    conn = sqlite3.connect('exercise_log.db')
    cursor = conn.cursor()
    # Query the database for the selected exercise
    cursor.execute('''
        SELECT Time, Max5
        FROM exercise_log
        WHERE Exercise = ?
        ORDER BY Time ASC
    ''', (selected_exercise,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return {}
    # Create a DataFrame from the query results
    df_chart = pd.DataFrame(rows, columns=['Time', 'Max5'])
    df_chart['Time'] = pd.to_datetime(df_chart['Time'])
    # Create the line chart
    fig = px.line(df_chart, x='Time', y='Max5', title=f'5Max Over Time for {selected_exercise}')
    return fig

# Run the app
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 80))
    app.run_server(debug=False, host='0.0.0.0', port=port)
