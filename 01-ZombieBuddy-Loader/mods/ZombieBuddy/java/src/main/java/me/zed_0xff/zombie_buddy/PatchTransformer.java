package me.zed_0xff.zombie_buddy;

import java.io.InputStream;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import net.bytebuddy.asm.Advice;
import net.bytebuddy.jar.asm.AnnotationVisitor;
import net.bytebuddy.jar.asm.ClassReader;
import net.bytebuddy.jar.asm.ClassVisitor;
import net.bytebuddy.jar.asm.ClassWriter;
import net.bytebuddy.jar.asm.MethodVisitor;
import net.bytebuddy.jar.asm.Opcodes;
import net.bytebuddy.jar.asm.Type;

/**
 * Transforms patch classes by replacing Patch.OnEnter/OnExit/Return annotations with 
 * net.bytebuddy.asm.Advice.* annotations in the class bytecode.
 * This allows mods to use Patch.* annotations without depending on ByteBuddy directly.
 */
final class PatchTransformer {
    private static final Type NO_EXCEPTION_HANDLER = Type.getType("Lnet/bytebuddy/asm/Advice$NoExceptionHandler;"); // private

    private static final Map<String, String> ADVICE_DESCRIPTOR_MAP;
    private static final Map<String, String> DELEGATION_DESCRIPTOR_MAP;
    private static final Map<Type, Type> TYPE_MAP;

    static {
        ADVICE_DESCRIPTOR_MAP = new HashMap<>();
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.OnEnter.class),          Type.getDescriptor(Advice.OnMethodEnter.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.OnExit.class),           Type.getDescriptor(Advice.OnMethodExit.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.Return.class),           Type.getDescriptor(Advice.Return.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.This.class),             Type.getDescriptor(Advice.This.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.Argument.class),         Type.getDescriptor(Advice.Argument.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.AllArguments.class),     Type.getDescriptor(Advice.AllArguments.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.Thrown.class),           Type.getDescriptor(Advice.Thrown.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.Local.class),            Type.getDescriptor(Advice.Local.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.RuntimeType.class),      Type.getDescriptor(net.bytebuddy.implementation.bind.annotation.RuntimeType.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.SuperMethod.class),      Type.getDescriptor(net.bytebuddy.implementation.bind.annotation.SuperMethod.class));
        ADVICE_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.SuperCall.class),        Type.getDescriptor(net.bytebuddy.implementation.bind.annotation.SuperCall.class));

        DELEGATION_DESCRIPTOR_MAP = new HashMap<>(ADVICE_DESCRIPTOR_MAP);
        DELEGATION_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.This.class),         Type.getDescriptor(net.bytebuddy.implementation.bind.annotation.This.class));
        DELEGATION_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.Argument.class),     Type.getDescriptor(net.bytebuddy.implementation.bind.annotation.Argument.class));
        DELEGATION_DESCRIPTOR_MAP.put(Type.getDescriptor(Patch.AllArguments.class), Type.getDescriptor(net.bytebuddy.implementation.bind.annotation.AllArguments.class));

        TYPE_MAP = new HashMap<>();
        TYPE_MAP.put(Type.getType(Patch.NoException.class),       NO_EXCEPTION_HANDLER);
        TYPE_MAP.put(Type.getType(Patch.OnDefaultValue.class),    Type.getType(Advice.OnDefaultValue.class));
        TYPE_MAP.put(Type.getType(Patch.OnNonDefaultValue.class), Type.getType(Advice.OnNonDefaultValue.class));
    }
    
    /**
     * Transforms a patch class by replacing Patch.OnEnter/OnExit/Return annotations with 
     * net.bytebuddy.asm.Advice.* annotations in the class bytecode.
     * This allows mods to use Patch.* annotations without depending on ByteBuddy directly.
     * 
     * @param patchClass The patch class to transform
     * @param instrumentation Instrumentation instance for class redefinition
     * @param verbosity Verbosity level for logging
     * @param isMethodDelegation Whether this is a MethodDelegation patch (true) or Advice patch (false)
     */
    public static Class<?> transformPatchClass(Class<?> patchClass, Instrumentation instrumentation, int verbosity, boolean isMethodDelegation) {
        try {
            // Check if transformation is needed and warn about non-void return types
            boolean needsTransformation = false;
            for (Method method : patchClass.getDeclaredMethods()) {
                boolean hasOnEnter     = method.isAnnotationPresent(Patch.OnEnter.class);
                boolean hasOnExit      = method.isAnnotationPresent(Patch.OnExit.class);
                boolean hasRuntimeType = method.isAnnotationPresent(Patch.RuntimeType.class);
                if (hasOnEnter || hasOnExit || hasRuntimeType) {
                    needsTransformation = true;
                }
                // Warn about non-void return types (check all methods, not just first one)
                if (hasOnEnter || hasOnExit) {
                    Class<?> returnType = method.getReturnType();
                    if (returnType != void.class) {
                        boolean hasSkipOnSet = false;
                        if (hasOnEnter) {
                            var ann = method.getAnnotation(Patch.OnEnter.class);
                            if (ann.skipOn()) hasSkipOnSet = true;
                        }
                        
                        if (!hasSkipOnSet) {
                            Logger.error("!!!!!!!");
                            Logger.error("WARNING: Annotated method " + method.getName() + "() in patch class " + patchClass.getName() + 
                                " returns non-void. This may cause UB and diarrhea.");
                            Logger.error("!!!!!!!");
                        }
                    }
                }
                if (!needsTransformation) {
                    for (java.lang.reflect.Parameter param : method.getParameters()) {
                        if (param.isAnnotationPresent(Patch.Return.class) ||
                            param.isAnnotationPresent(Patch.Thrown.class) ||
                            param.isAnnotationPresent(Patch.This.class) ||
                            param.isAnnotationPresent(Patch.Argument.class) ||
                            param.isAnnotationPresent(Patch.Local.class) ||
                            param.isAnnotationPresent(Patch.SuperMethod.class) ||
                            param.isAnnotationPresent(Patch.SuperCall.class)) {
                            needsTransformation = true;
                            break;
                        }
                    }
                }
            }

            if (verbosity > 1) {
                Logger.info("class " + patchClass.getName() + " needs transformation: " + needsTransformation);
            }
            
            if (!needsTransformation) {
                return patchClass; // Already uses ByteBuddy annotations or has no annotations
            }

            // Read class file bytes
            String className = patchClass.getName().replace('.', '/');
            String classFileName = className + ".class";
            InputStream classStream = patchClass.getClassLoader().getResourceAsStream(classFileName);
            if (classStream == null) {
                Logger.error("Could not read class file for " + patchClass.getName());
                return patchClass;
            }

            byte[] classBytes = classStream.readAllBytes();
            classStream.close();

            // Use ASM to rewrite annotation descriptors
            final boolean isMethodDelegationFinal = isMethodDelegation;
            ClassReader cr = new ClassReader(classBytes);
            ClassWriter cw = new ClassWriter(cr, ClassWriter.COMPUTE_FRAMES);
            cr.accept(new ClassVisitor(Opcodes.ASM9, cw) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
                    final boolean[] hasPatchAnnotation = {false};
                    final boolean[] hasSkipOnSet = {false};
                    
                    MethodVisitor mv = super.visitMethod(access, name, descriptor, signature, exceptions);
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
                            String newDescriptor = rewriteAnnotationDescriptor(descriptor, isMethodDelegationFinal);
                            
                            if (descriptor.equals(Type.getDescriptor(Patch.OnEnter.class)) ||
                                descriptor.equals(Type.getDescriptor(Patch.OnExit.class))  ||
                                descriptor.equals(Type.getDescriptor(Patch.RuntimeType.class))) {
                                hasPatchAnnotation[0] = true;
                            }
                            
                            AnnotationVisitor av = super.visitAnnotation(newDescriptor, visible);
                            // If we rewrote the descriptor, we need to forward all annotation values
                            if (!newDescriptor.equals(descriptor)) {
                                return new AnnotationVisitor(Opcodes.ASM9, av) {
                                    @Override
                                    public void visit(String name, Object value) {
                                        if ("skipOn".equals(name) && value instanceof Boolean skip) {
                                            hasSkipOnSet[0] = skip;
                                            // Translate boolean skipOn to ByteBuddy's expected Class<?> skipOn
                                            if (skip) {
                                                value = Type.getType(Advice.OnNonDefaultValue.class);
                                            } else {
                                                value = NO_EXCEPTION_HANDLER;
                                            }
                                        } else if (value instanceof Type type) {
                                            value = TYPE_MAP.getOrDefault(type, type);
                                        }
                                        super.visit(name, value);
                                    }
                                };
                            }
                            return av;
                        }

                        @Override
                        public AnnotationVisitor visitParameterAnnotation(int parameter, String descriptor, boolean visible) {
                            return super.visitParameterAnnotation(
                                    parameter,
                                    rewriteAnnotationDescriptor(descriptor, isMethodDelegationFinal),
                                    visible);
                        }
                    };
                }
            }, ClassReader.EXPAND_FRAMES);

            byte[] transformedBytes = cw.toByteArray();
            
            // Define the transformed class using Instrumentation
            if (instrumentation != null) {
                try {
                    java.lang.instrument.ClassDefinition classDef = new java.lang.instrument.ClassDefinition(patchClass, transformedBytes);
                    instrumentation.redefineClasses(classDef);
                    return patchClass; // Return the redefined class
                } catch (Exception e) {
                    Logger.error("Failed to redefine class " + patchClass.getName() + ": " + e.getMessage());
                    if (verbosity > 0) {
                        e.printStackTrace();
                    }
                }
            }
            
            // Fallback: try to define as a new class (won't work if class is already loaded)
            try {
                return (Class<?>) Accessor.callExact(patchClass.getClassLoader(), "defineClass",
                    new Class<?>[] { String.class, byte[].class, int.class, int.class },
                    patchClass.getName() + "$ZBTransformed", transformedBytes, 0, transformedBytes.length);
            } catch (Exception e) {
                Logger.error("Failed to define transformed class: " + e.getMessage());
                if (verbosity > 0) {
                    e.printStackTrace();
                }
            }
            
            return patchClass; // Fall back to original
        } catch (Exception e) {
            Logger.error("Failed to transform patch class " + patchClass.getName() + ": " + e.getMessage());
            if (verbosity > 0) {
                e.printStackTrace();
            }
            return patchClass; // Fall back to original
        }
    }

    private static String rewriteAnnotationDescriptor(String descriptor, boolean isMethodDelegation) {
        Map<String, String> map = isMethodDelegation ? DELEGATION_DESCRIPTOR_MAP : ADVICE_DESCRIPTOR_MAP;
        return map.getOrDefault(descriptor, descriptor);
    }
}
