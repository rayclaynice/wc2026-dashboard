import dash
from dash import dcc, html
import plotly.express as px
import plotly.graph_objects as go
import duckdb
import pandas as pd
import os







#  CONNECTION 
base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, 'data', 'wc2026.db')
conn = duckdb.connect(db_path, read_only=True)

# TABLES IN USE (PERSISTED IN wc2026 database)
# clean_elo, elo, top5_fifa






# QUERIES 
result1 = conn.execute("""
WITH
  country_and_confederation AS (
    SELECT
      COUNT(DISTINCT country) AS total_countries,
      COUNT(DISTINCT confederation) AS total_confederations
    FROM elo
    WHERE YEAR = '2026'
  ),
  host_count AS (
    SELECT
      COUNT(DISTINCT country) AS total_hosts
    FROM elo
    WHERE is_host = 1
  )
SELECT * FROM country_and_confederation CROSS JOIN host_count;
""").df()


result3 = conn.execute("""
WITH latest_2026 AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY country ORDER BY snapshot_date ASC
        ) AS rn
    FROM elo
    WHERE DATE_PART('year', snapshot_date) = 2026
)
SELECT snapshot_date, country, rank, confederation
FROM latest_2026
WHERE rn = 1
ORDER BY rank ASC
LIMIT 6
""").df()

result4 = conn.execute("""
SELECT team, RANK, points, association
FROM read_csv("data/fifa_ranking_2026-06-08.csv")
WHERE team IN (SELECT DISTINCT country FROM elo)
ORDER BY RANK ASC
LIMIT 10
""").df()

result5 = conn.execute("""
WITH
  current_year AS (
    SELECT snapshot_date, country, rating_avg, confederation
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY country ORDER BY snapshot_date ASC) AS rn
        FROM elo
        WHERE DATE_PART('year', snapshot_date) = 2026
    ) t
    WHERE rn = 1
  ),
  ten_years_ago AS (
    SELECT snapshot_date, country, rating_avg
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY country ORDER BY snapshot_date ASC) AS rn
        FROM elo
        WHERE DATE_PART('year', snapshot_date) = 2016
    ) t
    WHERE rn = 1
  )
SELECT
  c.country,
  c.rating_avg AS rating_2026,
  p.rating_avg AS rating_2016,
  (c.rating_avg - p.rating_avg) AS changes_over_time,
  c.confederation
FROM current_year c
JOIN ten_years_ago p ON c.country = p.country
ORDER BY changes_over_time ASC
""").df()

result6 = conn.execute("""
SELECT country, snapshot_date, rating_max, rating_avg,
  ROUND((rating_avg / rating_max) * 100, 1) AS consistency_score, confederation
FROM (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY country ORDER BY snapshot_date ASC) AS rn
    FROM elo
    WHERE DATE_PART('year', snapshot_date) = 2026
) t
WHERE rn = 1
ORDER BY rating_max DESC, consistency_score DESC
LIMIT 5;
""").df()

result7 = conn.execute("""
WITH yearly AS (
    SELECT 
        DATE_PART('year', snapshot_date) AS year,
        country, matches_total, wins, snapshot_date,
        LAG(matches_total) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_matches,
        LAG(wins) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_wins
    FROM clean_elo
),
difference_count AS (
    SELECT 
        year, country, snapshot_date,
        (matches_total - COALESCE(previous_matches, 0)) AS matches_per_year,
        (wins - COALESCE(previous_wins, 0)) AS wins_per_year
    FROM yearly
)
SELECT year, snapshot_date, country,
    ROUND((wins_per_year * 100.0) / NULLIF(matches_per_year, 0), 1) AS win_efficiency
FROM difference_count
WHERE year >= 2016
""").df()

result8 = conn.execute("""
SELECT confederation,
    ROUND(AVG(rating_avg), 1) AS confederation_power_index,
    COUNT(DISTINCT country) AS total_teams
FROM clean_elo
WHERE DATE_PART('year', snapshot_date) = 2026
GROUP BY confederation
HAVING COUNT(DISTINCT country) >= 3
ORDER BY confederation_power_index DESC;
""").df()

result9 = conn.execute("""
WITH conf_statistics AS (
    SELECT confederation,
        ROUND(STDDEV(rating_avg), 1) AS confederation_spread,
        COUNT(DISTINCT country) AS total_teams
    FROM clean_elo
    WHERE DATE_PART('year', snapshot_date) = 2026
    GROUP BY confederation
    HAVING COUNT(DISTINCT country) >= 3
)
SELECT confederation, total_teams, confederation_spread,
    CASE
        WHEN confederation_spread >= 170 THEN 'Highly Uneven'
        WHEN confederation_spread >= 130 THEN 'Moderately Uneven'
        ELSE 'Balanced'
    END AS con_balanced_label
FROM conf_statistics
""").df()

result10 = conn.execute("""
WITH top_10_last_10_years AS (
    SELECT country, snapshot_date, rank
    FROM clean_elo
    WHERE rank <= 10
    AND DATE_PART('year', snapshot_date) BETWEEN 2016 AND 2026
)
SELECT country, COUNT(*) AS years_in_top_10
FROM top_10_last_10_years
GROUP BY country
ORDER BY years_in_top_10 DESC;
""").df()

result11 = conn.execute("""
WITH trends AS (
    SELECT country,
        MIN(rating_avg) AS early_rating,
        MAX(rating_avg) AS recent_rating,
        MAX(rank) FILTER (WHERE DATE_PART('year', snapshot_date) = 2026) AS latest_rank
    FROM clean_elo
    WHERE DATE_PART('year', snapshot_date) BETWEEN 2016 AND 2026
    GROUP BY country
)
SELECT country, (recent_rating - early_rating) AS improvement, latest_rank
FROM trends
WHERE (recent_rating - early_rating) > 10
AND latest_rank BETWEEN 15 AND 30
ORDER BY improvement DESC;
""").df()

result12 = conn.execute("""
WITH yearly_goals AS (
    SELECT snapshot_date, country, goals_for, matches_total,
        LAG(matches_total) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_games,
        LAG(goals_for) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_goals_scored
    FROM clean_elo
    WHERE DATE_PART('year', snapshot_date) >= 2001
),
differences AS (
    SELECT country, snapshot_date,
        (matches_total - COALESCE(previous_games, 0)) AS matches_per_year,
        (goals_for - COALESCE(previous_goals_scored, 0)) AS goals_per_year,
        ROUND((goals_for - COALESCE(previous_goals_scored, 0)) * 1.0 /
            NULLIF((matches_total - COALESCE(previous_games, 0)), 0), 1) AS goals_per_match
    FROM yearly_goals
)
SELECT country, COUNT(*) AS high_scoring_years
FROM differences
WHERE matches_per_year >= 10 AND goals_per_match >= 2.2
GROUP BY country
ORDER BY high_scoring_years DESC
LIMIT 5
""").df()

result13 = conn.execute("""
WITH yearly_conceived_goals AS (
    SELECT snapshot_date, country, goals_against, matches_total,
        LAG(matches_total) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_games,
        LAG(goals_against) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_conceived_goals
    FROM clean_elo
    WHERE DATE_PART('year', snapshot_date) >= 2001
),
differences AS (
    SELECT country, snapshot_date,
        (matches_total - COALESCE(previous_games, 0)) AS matches_per_year,
        (goals_against - COALESCE(previous_conceived_goals, 0)) AS goals_conceded_per_year,
        ROUND((goals_against - COALESCE(previous_conceived_goals, 0)) * 1.0 /
            NULLIF((matches_total - COALESCE(previous_games, 0)), 0), 2) AS goals_conceded_per_match
    FROM yearly_conceived_goals
)
SELECT * FROM (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY defense_category ORDER BY avg_conceded_per_match ASC
        ) AS rn
    FROM (
        SELECT country,
            ROUND(AVG(goals_conceded_per_match), 1) AS avg_conceded_per_match,
            CASE
                WHEN AVG(goals_conceded_per_match) <= 0.8 THEN 'Elite Defense'
                WHEN AVG(goals_conceded_per_match) <= 1.2 THEN 'Solid Defense'
                WHEN AVG(goals_conceded_per_match) <= 1.6 THEN 'Weak Defense'
                ELSE 'Very Bad Defense'
            END AS defense_category
        FROM differences
        WHERE matches_per_year >= 10
        GROUP BY country
    ) t
) x
WHERE rn <= 5;
""").df()

result14 = conn.execute("""
WITH yearly_unbeaten AS (
    SELECT snapshot_date, country, wins, draws, matches_total,
        LAG(matches_total) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_games,
        LAG(wins) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_wins,
        LAG(draws) OVER (PARTITION BY country ORDER BY snapshot_date) AS previous_draws
    FROM clean_elo
    WHERE DATE_PART('year', snapshot_date) >= 2001
),
differences_c AS (
    SELECT country, snapshot_date,
        (matches_total - COALESCE(previous_games, 0)) AS matches_per_year,
        (wins - COALESCE(previous_wins, 0)) AS wins_per_year,
        (draws - COALESCE(previous_draws, 0)) AS draws_per_year,
        ROUND((((wins - COALESCE(previous_wins, 0)) + (draws - COALESCE(previous_draws, 0))) * 100.0) /
            NULLIF((matches_total - COALESCE(previous_games, 0)), 0), 1) AS unbeaten_rate_pct
    FROM yearly_unbeaten
)
SELECT country, COUNT(*) AS high_consistency_years
FROM differences_c
WHERE matches_per_year >= 10 AND unbeaten_rate_pct >= 80
GROUP BY country
ORDER BY high_consistency_years DESC
LIMIT 5
""").df()

result15 = conn.execute("""
WITH yearly_rank AS (
    SELECT year, country, goals_for,
        RANK() OVER (PARTITION BY year ORDER BY goals_for DESC) AS goals_rank
    FROM clean_elo
    WHERE year >= 1990
)
SELECT year, goals_rank, country, goals_for
FROM yearly_rank
WHERE goals_rank <= 10
ORDER BY year ASC, goals_rank ASC;
""").df()


# FIGURES

# metric cards
total_countries = result1["total_countries"].values[0]
total_confederations = result1["total_confederations"].values[0]
total_hosts = result1["total_hosts"].values[0]

total_cards = go.Figure()
total_cards.add_trace(go.Indicator(
    mode='number', value=total_countries,
    title={'text': 'Total Countries'},
    domain={"x": [0, 0.33], "y": [0, 1]}
))
total_cards.add_trace(go.Indicator(
    mode='number', value=total_hosts,
    title={'text': 'Total Hosts'},
    domain={"x": [0.33, 0.66], "y": [0, 1]}
))
total_cards.add_trace(go.Indicator(
    mode='number', value=total_confederations,
    title={'text': 'Total Confederations'},
    domain={"x": [0.66, 1.0], "y": [0, 1]}
))
total_cards.update_layout(template='plotly_dark', height=200)



fig3 = px.bar(
    result3, x='country', y='rank', color='confederation',
    title="Elo Team Ranking 2026",
    hover_data={'rank': True}, template='plotly_dark'
)
fig3.update_layout(yaxis_showgrid=False)

fig4 = px.bar(
    result4, x='team', y='points', template='plotly_dark',
     title="FIFA Team Ranking 2026",
    color='rank', labels={'points': 'Points', 'team': 'Teams', 'rank': 'Rank'}
)
fig4.update_layout(yaxis_showgrid=False, height=400, bargap=0.3)

fig5 = px.bar(
    result5, x='changes_over_time', y='country', color='confederation',
    orientation='h', title='Most Improved & Most Declined Teams (2016 - 2026)',
    template='plotly_dark', color_discrete_sequence=px.colors.qualitative.Set2
)
fig5.update_layout(
    xaxis_title='Rating Change', yaxis_title='Country', height=900,
    bargap=0.2, xaxis_showgrid=False, yaxis_showgrid=False,
    xaxis=dict(zeroline=True, zerolinecolor='white', zerolinewidth=1)
)

fig6 = px.scatter(
    result6, x='rating_max', y='consistency_score', color='confederation',
    size='consistency_score', text='country',
    title='Team Consistency vs Peak Rating 2026', template='plotly_dark'
)
fig6.update_traces(textposition='top center')
fig6.update_layout(
    xaxis_title='Peak Rating (All Time High)',
    yaxis_title='Consistency Score (%)',
    xaxis_showgrid=False, yaxis_showgrid=False, height=500
)

# fig7 
top5 = conn.execute("SELECT team FROM top5_fifa").df()['team'].tolist()
df_top5 = result7[result7['country'].isin(top5)].sort_values(['country', 'year'])
years = sorted(df_top5['year'].unique())
colors = px.colors.qualitative.Plotly

frames = []
for i in range(1, len(years) + 1):
    frame_data = []
    for j, country in enumerate(top5):
        df_country = df_top5[df_top5['country'] == country]
        subset = df_country[df_country['year'] <= years[i - 1]]
        frame_data.append(go.Scatter(
            x=subset['year'], y=subset['win_efficiency'], mode='lines',
            name=country, line=dict(color=colors[j % len(colors)], width=1, shape='spline')
        ))
    frames.append(go.Frame(data=frame_data, name=str(years[i - 1])))

initial_data = []
for j, country in enumerate(top5):
    df_country = df_top5[df_top5['country'] == country]
    first = df_country[df_country['year'] == years[0]]
    initial_data.append(go.Scatter(
        x=first['year'], y=first['win_efficiency'], mode='lines',
        name=country, line=dict(color=colors[j % len(colors)], width=1, shape='spline')
    ))

fig7 = go.Figure(data=initial_data, frames=frames)
fig7.update_layout(
    title='Win Efficiency Over Time, Top 5 FIFA Countries (2016-2026)-(Play Animation)',
    template='plotly_dark',
    xaxis=dict(range=[2016, 2026], showgrid=False),
    yaxis=dict(range=[0, 100], showgrid=False),
    height=600,
    updatemenus=[dict(
        type='buttons',
        buttons=[
            dict(label='Play', method='animate',
                 args=[None, dict(
                     frame=dict(duration=1500, redraw=True),
                     transition=dict(duration=1200),
                     fromcurrent=False, mode='immediate', loop=True
                 )]),
            dict(label='Pause', method='animate',
                 args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate')])
        ]
    )]
)

fig8 = px.bar(
    result8, y='confederation', x='confederation_power_index',
    title='Confederation Power Index', color='total_teams',
    template='plotly_dark',
    labels={"confederation_power_index": "Power Index",
            "confederation": "Confederation", "total_teams": "Number of Teams"}
)
fig8.update_layout(xaxis_showgrid=False, height=400, bargap=0.3)

fig9 = px.bar(
    result9, x='confederation', y='confederation_spread',
    title='How Balanced Are the Confederations Heading into 2026?',
    color='con_balanced_label', template='plotly_dark',
    labels={'confederation_spread': 'Confederation Spread',
            'confederation': 'Confederation', 'con_balanced_label': 'Balanced Label'},
    text='confederation_spread'
)
fig9.update_layout(yaxis_showgrid=False, height=400, bargap=0.2)

fig10 = px.bar(
    result10, y='country', x='years_in_top_10',
    title='Longest Time Spent in the Elo World Top 10',
    orientation='h', color='years_in_top_10',
    color_continuous_scale='Blues', template='plotly_dark',
    labels={'years_in_top_10': 'Years in Top 10', 'country': 'National Team'},
    text='years_in_top_10'
)
fig10.update_traces(textposition='outside', marker_line_color='white', marker_line_width=0.5)
fig10.update_layout(
    title=dict(font_size=24, x=0.5),
    xaxis_title="Years in Top 10 Elo", yaxis_title="",
    height=520, yaxis=dict(autorange="reversed"),
    bargap=0.3, showlegend=False
)

fig11 = px.bar(
    result11, y='country', x='improvement',
    title='The Silent Contenders/Rising Dark Horses for 2026',
    orientation='h', color='improvement',
    color_continuous_scale='Viridis', template='plotly_dark',
    text='improvement', hover_data=['latest_rank']
)
fig11.update_traces(texttemplate='+%{text:.1f}', textposition='outside')
fig11.update_layout(
    title=dict(font_size=22, x=0.5),
    xaxis_title="Elo Improvement (2016 → 2026)", yaxis_title="",
    height=500, yaxis=dict(autorange="reversed"),
    xaxis_showgrid=False, showlegend=False
)

fig12 = px.bar(
    result12, y='country', x='high_scoring_years',
    title='Most High-Scoring Seasons Since 2001',
    orientation='h', color='high_scoring_years',
    color_continuous_scale='Reds', template='plotly_dark',
    text='high_scoring_years'
)
fig12.update_traces(textposition='outside', marker_line_color='white', marker_line_width=1)
fig12.update_layout(
    title=dict(font_size=23, x=0.5),
    xaxis_title="Number of High-Scoring Seasons (≥2.2 goals/match)",
    yaxis_title="", height=420,
    yaxis=dict(autorange="reversed"),
    xaxis_showgrid=False, showlegend=False
)

fig13 = px.bar(
    result13, y='country', x='avg_conceded_per_match',
    title='Defensive Strength Since 2001', facet_col='defense_category',
    orientation='h', color='defense_category',
    color_discrete_map={
        'Elite Defense': '#00C853', 'Solid Defense': '#64DD17',
        'Weak Defense': '#FFB300', 'Very Bad Defense': '#FF1744'
    },
    template='plotly_dark', text='avg_conceded_per_match', height=700,
    labels={'avg_conceded_per_match': 'Avg Goals Conceded per Match', 'country': ''}
)
fig13.update_traces(texttemplate='%{text:.2f}', textposition='outside')
fig13.update_layout(
    title=dict(font_size=24, x=0.5),
    xaxis_title="Lower is Better ↓",
    showlegend=False, yaxis=dict(autorange="reversed")
)
fig13.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))

fig14 = px.bar(
    result14, y='country', x='high_consistency_years',
    title='Most Undefeated Seasons Since 2001',
    orientation='h', color='high_consistency_years',
    color_continuous_scale='Greens', template='plotly_dark',
    text='high_consistency_years', height=460
)
fig14.update_traces(textposition='outside', marker_line_color='white', marker_line_width=1.2)
fig14.update_layout(
    title=dict(font_size=23, x=0.5),
    xaxis_title="Number of High Consistency Seasons (≥80% Unbeaten)",
    yaxis_title="", yaxis=dict(autorange="reversed"),
    xaxis_showgrid=False, showlegend=False, margin=dict(t=80)
)

fig15 = px.bar(
    result15, x='goals_for', y='country', color='country',
    orientation='h', animation_frame='year', animation_group='country',
    title='Top Teams by Total Goals Scored (1990 - 2026)',
    template='plotly_dark', text='goals_for', height=720,
    labels={'goals_for': 'Cumulative Goals Scored'}
)
fig15.update_traces(
    texttemplate='%{text:,}', textposition='inside',
    textfont=dict(size=11, color='white'),
    marker_line_color='white', marker_line_width=0.6, width=0.7
)
fig15.update_layout(
    title=dict(font_size=24, x=0.5),
    xaxis_title="Total Goals Scored (All-Time)", yaxis_title="",
    yaxis=dict(autorange="reversed"),
    xaxis=dict(showgrid=False, range=[0, 3000]),
    bargap=0.45, showlegend=False,
    margin=dict(l=160, r=40, t=100, b=60)
)
fig15.layout.updatemenus[0].buttons[0].args[1]['frame']['duration'] = 800


#  DASH APP 
app = dash.Dash(__name__)
server = app.server

def section_header(title):
    return html.H2(title, style={
        'color': '#00D4AA', 'fontSize': '22px',
        'fontWeight': '500', 'marginBottom': '0.5rem',
        'marginTop': '1rem'
    })

def divider():
    return html.Hr(style={'borderColor': '#3d4155'})

def row(children):
    return html.Div(children, style={'display': 'flex', 'gap': '10px'})

def col(fig):
    return html.Div(
        dcc.Graph(figure=fig),
        style={'flex': '1', 'backgroundColor': '#1E2130',
               'border': '1px solid #5A6080', 'borderRadius': '12px', 'padding': '10px'}
    )

def full_width(fig):
    return html.Div(
        dcc.Graph(figure=fig),
        style={'backgroundColor': '#1E2130', 'border': '1px solid #5A6080',
               'borderRadius': '12px', 'padding': '10px', 'marginBottom': '10px'}
    )

app.layout = html.Div(
    style={'backgroundColor': '#111111', 'fontFamily': 'sans-serif', 'padding': '20px'},
    children=[

        #  TITLE 
        html.H1(
            '🏆 World Cup 2026 Dashboard',
            style={'color': '#00D4AA', 'textAlign': 'center', 'fontSize': '36px'}
        ),

        html.P(
            'A comprehensive analysis of all 48 qualified teams heading into the 2026 FIFA World Cup.',
            style={'color': 'white', 'textAlign': 'center', 'fontSize': '16px'}
        ),

        divider(),

        #  OVERVIEW 
        section_header('Overview'),
        full_width(total_cards),

        divider(),

        #  CURRENT RANKINGS 
        section_header('Current Rankings'),
        row([col(fig3), col(fig4)]),

        html.Div(style={'marginBottom': '10px'}),
        divider(),

        #  CONFEDERATION ANALYSIS 
        section_header('Confederation Analysis'),
        row([col(fig8), col(fig9)]),

        html.Div(style={'marginBottom': '10px'}),
        divider(),

        #  HISTORICAL DOMINANCE 
        section_header('Historical Dominance'),
        full_width(fig10),

        html.Div(style={'marginBottom': '10px'}),
        divider(),

        #  PERFORMANCE TRENDS 
        section_header('Performance Trends (2016 - 2026)'),
        full_width(fig5),
        full_width(fig7),

        html.Div(style={'marginBottom': '10px'}),
        divider(),

        #  ATTACKING STRENGTH 
        section_header('Attacking Strength'),
        row([col(fig12), col(fig14)]),

        html.Div(style={'marginBottom': '10px'}),
        divider(),

        #  DEFENSIVE STRENGTH 
        section_header('Defensive Strength'),
        full_width(fig13),

        html.Div(style={'marginBottom': '10px'}),
        divider(),

        #  DARK HORSES & CONSISTENCY 
        section_header('Dark Horses & Consistency'),
        row([col(fig11), col(fig6)]),

        html.Div(style={'marginBottom': '10px'}),
        divider(),

        #  GOALS RACE 
        section_header('Goals Race (1990 - 2026)'),
        full_width(fig15),

        divider(),

        #  FOOTER 
        html.Div([
    html.Hr(style={'borderColor': '#3d4155'}),
    html.P(
        '📊 Data Sources:',
        style={'color': '#00D4AA', 'fontWeight': 'bold', 'marginBottom': '5px'}
    ),
    html.P(
        'Elo Ratings: World Football Elo Ratings (eloratings.net) · License: CC BY-SA 4.0',
        style={'color': '#888', 'fontSize': '13px'}
    ),
    html.P(
        'FIFA Rankings: FIFA.com (June 2026)',
        style={'color': '#888', 'fontSize': '13px', 'marginTop': '3px'}
    ),
    html.P(
        'Built with Dash & Plotly · World Cup 2026 Analysis · Abasifreke Ukpong · 2026',
        style={'color': '#666', 'fontSize': '13px', 'marginTop': '5px'}
    )
], style={'textAlign': 'center', 'marginTop': '2rem', 'padding': '20px'})
    ]
)

if __name__ == '__main__':
    app.run(debug=True)