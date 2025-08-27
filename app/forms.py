from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
from app.models import User
from flask_login import current_user

# Validador customizado para aceitar números com vírgula ou ponto
def validate_decimal(form, field):
    if field.data:
        value = str(field.data).replace(',', '.')
        try:
            float(value)
        except ValueError:
            raise ValidationError('Por favor, insira um número válido.')

class RegistrationForm(FlaskForm):
    full_name = StringField('Nome Completo', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    business_name = StringField('Nome do Negócio', validators=[DataRequired(), Length(min=2, max=100)])
    business_type = SelectField('Tipo de Negócio', choices=[
        ('Padaria', 'Padaria'), ('Confeitaria / Doceria', 'Confeitaria / Doceria'), ('Pizzaria', 'Pizzaria'),
        ('Hamburgueria', 'Hamburgueria'), ('Restaurante', 'Restaurante'), ('Lanchonete', 'Lanchonete'),
        ('Food Truck', 'Food Truck'), ('Outro', 'Outro')
    ], validators=[DataRequired()])
    phone = StringField('Telefone / WhatsApp', validators=[Optional()])
    password = PasswordField('Senha', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password', message='As senhas devem ser iguais.')])
    submit = SubmitField('Criar Conta e Começar')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Este e-mail já está em uso. Por favor, escolha outro.')

class LoginForm(FlaskForm):
    email = StringField('Seu E-mail', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

class IngredientForm(FlaskForm):
    name = StringField('Nome do Ingrediente', validators=[DataRequired()])
    # MUDANÇA: FloatField para StringField com nosso validador
    package_price = StringField('Preço Pago no Pacote (R$)', validators=[DataRequired(), validate_decimal])
    package_quantity = StringField('Quantidade no Pacote', validators=[DataRequired(), validate_decimal])
    package_unit = SelectField('Unidade do Pacote', choices=[
        ('kg', 'Quilograma (kg)'), ('g', 'Grama (g)'), ('l', 'Litro (l)'), 
        ('ml', 'Mililitro (ml)'), ('un', 'Unidade (un)')
    ], validators=[DataRequired()])
    submit = SubmitField('Salvar Ingrediente')
    
class UpdateProfileForm(FlaskForm):
    full_name = StringField('Nome Completo', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    business_name = StringField('Nome do Negócio', validators=[DataRequired(), Length(min=2, max=100)])
    business_type = SelectField('Tipo de Negócio', choices=[
        ('Padaria', 'Padaria'), ('Confeitaria / Doceria', 'Confeitaria / Doceria'), ('Pizzaria', 'Pizzaria'),
        ('Hamburgueria', 'Hamburgueria'), ('Restaurante', 'Restaurante'), ('Lanchonete', 'Lanchonete'),
        ('Food Truck', 'Food Truck'), ('Outro', 'Outro')
    ], validators=[DataRequired()])
    phone = StringField('Telefone / WhatsApp', validators=[Optional()])
    submit = SubmitField('Salvar Alterações')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('Este e-mail já está em uso por outra conta.')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Senha Atual', validators=[DataRequired()])
    new_password = PasswordField('Nova Senha', validators=[DataRequired(), Length(min=6)])
    confirm_new_password = PasswordField('Confirmar Nova Senha', validators=[DataRequired(), EqualTo('new_password', message='As senhas devem ser iguais.')])
    submit_password = SubmitField('Alterar Senha')