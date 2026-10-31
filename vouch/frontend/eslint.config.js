import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import hooks from 'eslint-plugin-react-hooks'
export default tseslint.config(js.configs.recommended, ...tseslint.configs.recommended, {
  files: ['src/**/*.{ts,tsx}'],
  plugins: {'react-hooks': hooks},
  rules: {
    'react-hooks/rules-of-hooks': 'error', 'react-hooks/exhaustive-deps': 'warn',
    '@typescript-eslint/no-explicit-any': 'error',
    'no-restricted-syntax': ['error',
      {selector:'JSXAttribute[name.name="dangerouslySetInnerHTML"]',message:'CV-derived content must be rendered as text.'},
      {selector:'MemberExpression[property.name="innerHTML"]',message:'Use text nodes, never HTML injection.'}]
  }
})
