from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
import smtplib
import json
import random
import string
import re
import openpyxl
from dotenv import load_dotenv
from email.mime.text import MIMEText
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from flask import make_response
import psycopg2
from psycopg2.extras import DictCursor
from urllib.parse import urlparse

logging.basicConfig(level=logging.DEBUG)
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

(''
 '')


def create_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Criação da tabela de usuários (exemplo)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios_cadastros (
                id SERIAL PRIMARY KEY,
                nome_completo VARCHAR(255) NOT NULL,
                usuario VARCHAR(255) UNIQUE NOT NULL,
                senha VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                verificado BOOLEAN DEFAULT FALSE
            );
        """)

        # Criação da tabela de atividades (exemplo)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tempo_atividade (
                id SERIAL PRIMARY KEY,
                categoria VARCHAR(255),
                ambito VARCHAR(255),
                empresa_nome VARCHAR(255),
                codigo VARCHAR(50),
                tributo VARCHAR(255),
                atividade_selecionada TEXT,
                dia_inicio DATE,
                hora_inicio TIME,
                dia_termino DATE,
                hora_termino TIME,
                tempo_conclusao INTERVAL,
                responsavel VARCHAR(255)
            );
        """)

        # Criação da tabela de justificativas (exemplo)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS justificativa (
                id SERIAL PRIMARY KEY,
                categoria VARCHAR(255),
                ambito VARCHAR(255),
                empresa_nome VARCHAR(255),
                codigo VARCHAR(50),
                tributo VARCHAR(255),
                dia_inicio DATE,
                hora_inicio TIME,
                hora_inicio_pausa TIME,
                tempo_inicio INTERVAL,
                responsavel VARCHAR(255),
                justificativa TEXT
            );
        """)

        conn.commit()
        logging.debug("Tabelas criadas com sucesso!")
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao criar as tabelas: {e}")
    finally:
        cur.close()
        conn.close()

# Chama a função create_tables ao iniciar o app
create_tables()


def get_db_connection():
    DATABASE_URL = os.getenv('DATABASE_URL')
    result = urlparse(DATABASE_URL)
    connection = psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )
    return connection


def send_email(to_email, subject, body):
    from_email = os.getenv('EMAIL_USER')
    email_password = os.getenv('EMAIL_PASSWORD')
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT'))

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.set_debuglevel(1)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(from_email, email_password)
        server.sendmail(from_email, to_email, msg.as_string())
        logging.debug("E-mail enviado com sucesso!")
        server.quit()
    except smtplib.SMTPAuthenticationError as auth_err:
        logging.error(f"Erro de autenticação ao enviar e-mail: {auth_err.smtp_code} - {auth_err.smtp_error}")
        raise auth_err
    except Exception as e:
        logging.error(f"Erro ao enviar e-mail: {e}")
        raise e


def generate_verification_code(length=7):
    characters = string.ascii_uppercase + string.ascii_lowercase + string.digits + string.punctuation
    return ''.join(random.choices(characters, k=length))


def validate_password(password):
    has_upper = re.search(r'[A-Z]', password) is not None
    has_number = re.search(r'[0-9]', password) is not None
    has_special = re.search(r'[!@#$%^&*(),.?":{}|<>]', password) is not None
    is_long_enough = len(password) >= 7
    return has_upper, has_number, has_special, is_long_enough


def validate_email_and_username(email, username):
    if not email.endswith('@mangels.com.br'):
        return False, "O e-mail deve ser do domínio @mangels.com.br."

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT email FROM usuarios_cadastros WHERE email = %s", (email,))
        if cur.fetchone():
            return False, "Este e-mail já está cadastrado."

        cur.execute("SELECT usuario FROM usuarios_cadastros WHERE usuario = %s", (username,))
        if cur.fetchone():
            return False, "Este nome de usuário já está em uso."

        return True, "E-mail e nome de usuário disponíveis."
    finally:
        cur.close()
        conn.close()


def save_user_to_database(full_name, username, email, password, verified="Não"):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        hashed_password = generate_password_hash(password)
        cur.execute("""
            INSERT INTO usuarios_cadastros (nome_completo, usuario, senha, email, verificado)
            VALUES (%s, %s, %s, %s, %s)
        """, (full_name, username, hashed_password, email, verified == "Sim"))
        conn.commit()
        logging.debug(f"Usuário {username} salvo no banco com sucesso!")
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao salvar usuário: {e}")
        raise e
    finally:
        cur.close()
        conn.close()


def is_logged_in():
    return 'user' in session


@app.route('/')
def index():
    return redirect(url_for('login_page'))


@app.route('/login_page')
def login_page():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    if not username or not password:
        flash("Todos os campos são obrigatórios!", "danger")
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("SELECT * FROM usuarios_cadastros WHERE usuario = %s", (username,))
        user = cur.fetchone()

        if user and check_password_hash(user['senha'], password):
            session['user'] = username
            flash(f"Bem-vindo, {username}!", "success")
            return redirect(url_for('home_page'))
        else:
            flash("Usuário ou senha incorretos.", "danger")
            return redirect(url_for('login_page'))
    finally:
        cur.close()
        conn.close()


@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'GET':
        return render_template('create_account.html')

    full_name = request.form['full_name']
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    verification_code = generate_verification_code()

    if not full_name or not username or not email or not password:
        flash("Todos os campos são obrigatórios!", "danger")
        return redirect(url_for('create_account'))

    if not all(validate_password(password)):
        flash("A senha deve conter pelo menos uma letra maiúscula, um caractere especial e um número.", "danger")
        return redirect(url_for('create_account'))

    is_valid, message = validate_email_and_username(email, username)
    if not is_valid:
        flash(message, "danger")
        return redirect(url_for('create_account'))

    try:
        send_email(email, "Código de Verificação", f"Seu código de verificação é: {verification_code}")
        save_user_to_database(full_name, username, email, password)
        return render_template('verify.html', email=email, code=verification_code)
    except Exception as e:
        flash(f"Erro ao criar conta: {e}", "danger")
        return redirect(url_for('create_account'))


@app.route('/verify', methods=['POST'])
def verify():
    email = request.form['email']
    code = request.form['code']
    submitted_code = request.form['submitted_code']

    if code != submitted_code:
        flash("Código de verificação incorreto!", "danger")
        return render_template('verify.html', email=email, code=code)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios_cadastros SET verificado = TRUE WHERE email = %s", (email,))
        conn.commit()
        flash("Conta verificada com sucesso!", "success")
        return redirect(url_for('login_page'))
    except Exception as e:
        conn.rollback()
        flash("Erro ao verificar conta.", "danger")
        return render_template('verify.html', email=email, code=code)
    finally:
        cur.close()
        conn.close()


@app.route('/recover_password', methods=['GET', 'POST'])
def recover_password():
    if request.method == 'GET':
        return render_template('recover_password.html')

    email = request.form['email']
    if not email:
        flash("O campo de e-mail não pode estar vazio.", "danger")
        return redirect(url_for('recover_password'))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM usuarios_cadastros WHERE email = %s", (email,))
        user = cur.fetchone()
        if user:
            verification_code = generate_verification_code()
            send_email(email, "Recuperação de Senha", f"Seu código de recuperação é: {verification_code}")
            return render_template('verify_password.html', email=email, code=verification_code)
        else:
            flash("E-mail não encontrado.", "danger")
            return redirect(url_for('recover_password'))
    finally:
        cur.close()
        conn.close()


@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.form['email']
    new_password = request.form['new_password']

    if not all(validate_password(new_password)):
        flash("A senha deve conter pelo menos uma letra maiúscula, um caractere especial e um número.", "danger")
        return render_template('reset_password.html', email=email)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        hashed_password = generate_password_hash(new_password)
        cur.execute("UPDATE usuarios_cadastros SET senha = %s WHERE email = %s", (hashed_password, email))
        conn.commit()
        flash("Senha redefinida com sucesso!", "success")
        return redirect(url_for('login_page'))
    except Exception as e:
        conn.rollback()
        flash("Erro ao redefinir senha.", "danger")
        return render_template('reset_password.html', email=email)
    finally:
        cur.close()
        conn.close()


@app.route('/saveActivity', methods=['POST'])
def save_activity():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO tempo_atividade (
                categoria, ambito, empresa_nome, codigo, tributo,
                atividade_selecionada, dia_inicio, hora_inicio,
                dia_termino, hora_termino, tempo_conclusao, responsavel
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['categoria'], data['ambito'], data['empresaNome'],
            data['codigo'], data['tributo'], data['atividadeSelecionada'],
            data['diaInicio'], data['horaInicio'], data['diaTermino'],
            data['horaTermino'], data['tempoConclusao'], data['responsavel']
        ))
        conn.commit()
        return jsonify(message="Atividade salva com sucesso!"), 200
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao salvar atividade: {e}")
        return jsonify(message="Erro ao salvar a atividade."), 500
    finally:
        cur.close()
        conn.close()


@app.route('/saveJustificativa', methods=['POST'])
def save_justificativa():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO justificativa (
                categoria, ambito, empresa_nome, codigo, tributo,
                dia_inicio, hora_inicio, hora_inicio_pausa,
                tempo_inicio, responsavel, justificativa
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['atividade'], data['Âmbito'], data['Empresa Nome'],
            data['Código'], data['Tributo'], data['diaInicio'],
            data['horaInicio'], data['horaInicioDaPausa'],
            data['tempoDeInicio'], data['responsavel'], data['justificativa']
        ))
        conn.commit()
        return jsonify(message="Justificativa salva com sucesso!"), 200
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao salvar justificativa: {e}")
        return jsonify(message="Erro ao salvar a justificativa."), 500
    finally:
        cur.close()
        conn.close()


@app.route('/home_page')
def home_page():
    if not is_logged_in():
        return redirect(url_for('login_page'))
    return render_template('home.html', username=session['user'])


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/check_session')
def check_session():
    if 'user' in session:
        return '', 200
    return '', 401


@app.after_request
def add_security_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


if __name__ == '__main__':
    app.run(debug=True)

