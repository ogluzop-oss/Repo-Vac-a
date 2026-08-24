/**
 * Pantalla de Login. Consume el auth oficial del servidor (usuario/contraseña + empresa opcional) y
 * gestiona el reto MFA cuando el backend responde `mfa_required` (2º factor activo).
 */
import React, {useState} from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {useAuth} from '@/store/AuthContext';
import {colors} from '@/theme/colors';

export default function LoginScreen() {
  const {status, signIn, submitMfa, usuario: usuarioActivo} = useAuth();
  const [usuario, setUsuario] = useState('');
  const [password, setPassword] = useState('');
  const [empresa, setEmpresa] = useState('');
  const [codigo, setCodigo] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const enMfa = status === 'mfaRequired';

  async function onSubmit() {
    setError(null);
    setLoading(true);
    try {
      if (enMfa) {
        const r = await submitMfa(codigo.trim());
        if (r.kind === 'error') {
          setError('Código MFA incorrecto.');
        }
      } else {
        const idEmpresa = empresa.trim() ? Number(empresa.trim()) : undefined;
        const r = await signIn(usuario.trim(), password, idEmpresa);
        if (r.kind === 'error') {
          setError(
            r.status === 401
              ? 'Usuario o contraseña incorrectos.'
              : `No se pudo iniciar sesión (${r.error}).`,
          );
        }
      }
    } catch {
      setError('No hay conexión con el servidor. Revisa API_HOST.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.card}>
        <Text style={styles.brand}>SMART MANAGER</Text>
        <Text style={styles.subtitle}>
          {enMfa ? 'Verificación en dos pasos' : 'Acceso'}
        </Text>

        {enMfa ? (
          <>
            <Text style={styles.hint}>
              Introduce el código de tu app de autenticación
              {usuarioActivo ? ` (${usuarioActivo})` : ''}.
            </Text>
            <TextInput
              style={styles.input}
              placeholder="Código de 6 dígitos"
              placeholderTextColor={colors.textDim}
              keyboardType="number-pad"
              value={codigo}
              onChangeText={setCodigo}
              autoFocus
            />
          </>
        ) : (
          <>
            <TextInput
              style={styles.input}
              placeholder="Usuario"
              placeholderTextColor={colors.textDim}
              autoCapitalize="none"
              value={usuario}
              onChangeText={setUsuario}
            />
            <TextInput
              style={styles.input}
              placeholder="Contraseña"
              placeholderTextColor={colors.textDim}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />
            <TextInput
              style={styles.input}
              placeholder="ID empresa (opcional)"
              placeholderTextColor={colors.textDim}
              keyboardType="number-pad"
              value={empresa}
              onChangeText={setEmpresa}
            />
          </>
        )}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={onSubmit}
          disabled={loading}>
          {loading ? (
            <ActivityIndicator color={colors.bg} />
          ) : (
            <Text style={styles.buttonText}>
              {enMfa ? 'Verificar' : 'Entrar'}
            </Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg, justifyContent: 'center', padding: 24},
  card: {
    backgroundColor: colors.panel,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 24,
  },
  brand: {
    color: colors.cyan,
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: 2,
    textAlign: 'center',
  },
  subtitle: {color: colors.textDim, textAlign: 'center', marginTop: 4, marginBottom: 18},
  hint: {color: colors.textDim, marginBottom: 12},
  input: {
    backgroundColor: colors.bg,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 12,
    fontSize: 16,
  },
  error: {color: colors.danger, marginBottom: 12},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 4,
  },
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '900', fontSize: 16, letterSpacing: 1},
});
