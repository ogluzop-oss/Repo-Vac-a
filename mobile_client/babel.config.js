module.exports = {
  presets: ['module:@react-native/babel-preset'],
  plugins: [
    // Resuelve el alias "@/..." → "src/..." (Metro/Babel no leen los paths de tsconfig).
    [
      'module-resolver',
      {
        root: ['./'],
        alias: {'@': './src'},
        extensions: ['.ts', '.tsx', '.js', '.jsx', '.json'],
      },
    ],
  ],
};
